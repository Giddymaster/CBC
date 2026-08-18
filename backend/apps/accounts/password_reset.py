"""Forgot-password: prove you hold the phone or email on file, then set a new one.

Two ways in, both over the verification core:
- **SMS** — a 6-digit code texted to the number, entered back with the new
  password.
- **Email** — a magic link; the page it opens sets the new password against the
  link's token.

The request step always answers the same, whether or not the account exists, so
the form is not an account-existence oracle. The channel shown to the user is
inferred from what THEY typed (an email address vs a phone number), not from any
lookup, so that neutrality holds.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import Verification
from .verification import (
    VerifyResult,
    confirm_code,
    consume_token,
    request_verification,
)

User = get_user_model()


def _looks_like_email(text):
    return "@" in text and "." in text.split("@")[-1]


def _clean_phone(text):
    digits = "".join(ch for ch in text if ch.isdigit())
    if digits.startswith("0"):
        digits = "254" + digits[1:]
    elif digits.startswith(("7", "1")) and len(digits) == 9:
        digits = "254" + digits
    return digits if len(digits) >= 12 else ""


def _resolve(identifier):
    """(user, channel, target) for what was typed — or (None, channel, '') so
    the caller can behave identically for a miss."""
    text = (identifier or "").strip()
    if _looks_like_email(text):
        user = User.objects.filter(email__iexact=text).first()
        return user, Verification.Channel.EMAIL, text
    phone = _clean_phone(text)
    if phone:
        user = User.objects.filter(phone=phone).first()
        return user, Verification.Channel.SMS, phone
    # A username — send to whatever contact the account has, email first.
    user = User.objects.filter(username__iexact=text).first()
    if user and user.email:
        return user, Verification.Channel.EMAIL, user.email
    if user and user.phone:
        return user, Verification.Channel.SMS, user.phone
    return None, Verification.Channel.EMAIL, ""


def _channel_hint(identifier):
    text = (identifier or "").strip()
    if _looks_like_email(text):
        return "EMAIL"
    return "SMS" if _clean_phone(text) else "EMAIL"


def _set_password(user, new_password):
    try:
        validate_password(new_password, user=user)
    except DjangoValidationError as exc:
        raise serializers.ValidationError({"new_password": list(exc.messages)})
    user.set_password(new_password)
    user.must_change_password = False
    user.password_changed_at = timezone.now()
    user.save(update_fields=["password", "must_change_password", "password_changed_at"])
    # A reset is a response to a lost or compromised password — old sessions die.
    Token.objects.filter(user=user).delete()


class PasswordResetOptionsView(APIView):
    """POST /api/password-reset/options/ {identifier} — where a reset can go.

    Returns the account's contacts masked (****0111, j***@gmail.com) so the
    form can offer a choice, or send straight to the only one. An unknown
    identifier returns an empty list — the page shows the same neutral message
    it always did, and the endpoint is throttled, so this stays a poor
    enumeration tool while making the real flow honest about where the code
    went.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = "verify"
    throttle_classes = [ScopedRateThrottle]

    def post(self, request):
        user, _, _ = _resolve(request.data.get("identifier") or "")
        options = []
        if user is not None:
            if user.phone:
                options.append({"channel": "SMS", "target": _mask(user.phone)})
            if user.email:
                options.append({"channel": "EMAIL", "target": _mask(user.email)})
        return Response({"options": options})


class PasswordResetRequestView(APIView):
    """POST /api/password-reset/request/ {identifier, channel?} — email, phone
    or username; the optional channel picks which contact when there are two."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = "verify"
    throttle_classes = [ScopedRateThrottle]

    def post(self, request):
        identifier = request.data.get("identifier") or ""
        wanted = (request.data.get("channel") or "").upper()
        user, channel, target = _resolve(identifier)
        if user is not None:
            # A chosen channel overrides the guess from the identifier's shape.
            if wanted == "SMS" and user.phone:
                channel, target = Verification.Channel.SMS, user.phone
            elif wanted == "EMAIL" and user.email:
                channel, target = Verification.Channel.EMAIL, user.email
        if user is not None and target:
            request_verification(
                channel=channel,
                purpose=Verification.Purpose.PASSWORD_RESET,
                target=target,
                user=user,
                school=user.school,
            )
        # Identical response whether or not the account exists.
        return Response(
            {
                "detail": "If that account exists, we've sent a way to reset it.",
                "channel": wanted or _channel_hint(identifier),
            }
        )


class PasswordResetConfirmView(APIView):
    """POST /api/password-reset/confirm/ — {token, new_password} for a link, or
    {identifier, code, new_password} for an SMS code."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = "verify"
    throttle_classes = [ScopedRateThrottle]

    def post(self, request):
        new_password = request.data.get("new_password") or ""
        if not new_password:
            return Response(
                {"new_password": ["Choose a new password."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        token = request.data.get("token")
        if token:
            record = consume_token(token, purpose=Verification.Purpose.PASSWORD_RESET)
            if record is None or record.user is None:
                return Response(
                    {"detail": "This reset link is invalid or has expired."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            _set_password(record.user, new_password)
            return Response({"detail": "Password set. Sign in with your new password."})

        # Code path (texted, or read out of the email). The record is found by
        # the account the identifier resolves to, not the typed target — the
        # user may have typed a username while the code went to their phone.
        user, _, _ = _resolve(request.data.get("identifier") or "")
        record = (
            Verification.objects.filter(
                purpose=Verification.Purpose.PASSWORD_RESET,
                user=user,
                consumed_at__isnull=True,
            ).order_by("-created_at").first()
            if user is not None
            else None
        )
        result = confirm_code(record, request.data.get("code"))
        if result != VerifyResult.OK or record.user is None:
            return Response(
                {"detail": "That code is wrong or has expired."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        _set_password(record.user, new_password)
        return Response({"detail": "Password set. Sign in with your new password."})


class VerificationPeekView(APIView):
    """GET /api/verify/<token>/ — what a magic link is for, without spending it,
    so the page it opens knows which form to show and who it belongs to."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, token):
        record = Verification.objects.filter(
            token=token, consumed_at__isnull=True
        ).select_related("user").first()
        if record is None or record.expires_at <= timezone.now():
            return Response(
                {"valid": False, "detail": "This link is invalid or has expired."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {
                "valid": True,
                "purpose": record.purpose,
                "target": _mask(record.target),
                "name": record.user.get_full_name() if record.user else "",
            }
        )


def _mask(target):
    """Show enough to recognise, not enough to harvest: a****@x.com, ****6789."""
    if "@" in target:
        name, _, domain = target.partition("@")
        head = name[0] if name else ""
        return f"{head}***@{domain}"
    return f"****{target[-4:]}" if len(target) >= 4 else "****"
