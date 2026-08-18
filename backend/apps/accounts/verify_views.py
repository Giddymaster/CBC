"""Contact verification and the 2FA switch — thin views over the engine.

Verifying a phone or email is the same three steps everywhere: ask for a code
to your own contact, type it back (or tap the emailed link), and the account's
verified flag flips. The flags then mean something: two-factor sign-in can only
be switched on once at least one contact is verified, because a second factor
sent to an unreachable channel is a lockout, not a protection.
"""

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import Verification
from .verification import VerifyResult, confirm_code, consume_token, request_verification

CONTACT_PURPOSES = (
    Verification.Purpose.PHONE_VERIFY,
    Verification.Purpose.EMAIL_VERIFY,
)


def mask(target):
    """a****@x.com / ****6789 — recognisable, not harvestable."""
    if "@" in target:
        name, _, domain = target.partition("@")
        return f"{name[:1]}***@{domain}"
    return f"****{target[-4:]}" if len(target) >= 4 else "****"


def mark_verified(user, purpose):
    if purpose == Verification.Purpose.PHONE_VERIFY:
        user.phone_verified = True
        user.save(update_fields=["phone_verified"])
    elif purpose == Verification.Purpose.EMAIL_VERIFY:
        user.email_verified = True
        user.save(update_fields=["email_verified"])


def start_contact_verification(user, school=None):
    """Kick off verification for whatever contact an account has — email link
    if there is an email (free), else an SMS code. Called when accounts are
    created; never raises, because a failed notice must not block the creation
    that triggered it."""
    try:
        if user.email:
            request_verification(
                channel=Verification.Channel.EMAIL,
                purpose=Verification.Purpose.EMAIL_VERIFY,
                target=user.email,
                user=user,
                school=school or user.school,
            )
        elif user.phone:
            request_verification(
                channel=Verification.Channel.SMS,
                purpose=Verification.Purpose.PHONE_VERIFY,
                target=user.phone,
                user=user,
                school=school or user.school,
            )
    except Exception:  # pragma: no cover — best-effort by design
        import logging

        logging.getLogger(__name__).exception("contact verification send failed")


class MyVerifyRequestView(APIView):
    """POST /api/me/verify/request/ {channel: SMS|EMAIL} — a code to my own
    contact on file. Under /api/me/ so it works even during a forced password
    change."""

    throttle_scope = "verify"
    throttle_classes = [ScopedRateThrottle]

    def post(self, request):
        user = request.user
        channel = (request.data.get("channel") or "").upper()
        if channel == "SMS":
            if not user.phone:
                return Response({"detail": "No phone number on your account."}, status=400)
            record = request_verification(
                channel=Verification.Channel.SMS,
                purpose=Verification.Purpose.PHONE_VERIFY,
                target=user.phone,
                user=user,
                school=user.school,
            )
        elif channel == "EMAIL":
            if not user.email:
                return Response({"detail": "No email on your account."}, status=400)
            record = request_verification(
                channel=Verification.Channel.EMAIL,
                purpose=Verification.Purpose.EMAIL_VERIFY,
                target=user.email,
                user=user,
                school=user.school,
            )
        else:
            return Response({"detail": "channel must be SMS or EMAIL."}, status=400)
        return Response({"sent": True, "target": mask(record.target), "channel": channel})


class MyVerifyConfirmView(APIView):
    """POST /api/me/verify/confirm/ {code} — flips the matching verified flag."""

    throttle_scope = "verify"
    throttle_classes = [ScopedRateThrottle]

    def post(self, request):
        record = (
            Verification.objects.filter(
                user=request.user,
                purpose__in=CONTACT_PURPOSES,
                consumed_at__isnull=True,
            )
            .order_by("-created_at")
            .first()
        )
        result = confirm_code(record, request.data.get("code"))
        if result != VerifyResult.OK:
            return Response(
                {"detail": "That code is wrong or has expired."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        mark_verified(request.user, record.purpose)
        return Response({"verified": record.purpose})


class VerifyLinkConfirmView(APIView):
    """POST /api/verify/confirm-link/ {token} — the emailed tap-to-verify link.
    Unauthenticated: the recipient may open it on a device with no session."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = "verify"
    throttle_classes = [ScopedRateThrottle]

    def post(self, request):
        record = consume_token(request.data.get("token") or "")
        if record is None or record.user is None or record.purpose not in CONTACT_PURPOSES:
            return Response(
                {"detail": "This link is invalid or has expired."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        mark_verified(record.user, record.purpose)
        return Response({"verified": record.purpose, "target": mask(record.target)})


class TwoFactorView(APIView):
    """POST /api/me/2fa/ {enabled: true|false}.

    Switching ON requires a verified contact — a code sent to an unverified
    channel could be a code sent to nobody, and that is a lockout."""

    def post(self, request):
        user = request.user
        enabled = bool(request.data.get("enabled"))
        if enabled and not (user.phone_verified or user.email_verified):
            return Response(
                {"detail": "Verify your phone or email first, so sign-in codes can reach you."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.two_factor_enabled = enabled
        user.save(update_fields=["two_factor_enabled"])
        return Response({"two_factor_enabled": enabled})


def latest_login_code(user):
    return (
        Verification.objects.filter(
            user=user,
            purpose=Verification.Purpose.LOGIN_2FA,
            consumed_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
        .order_by("-created_at")
        .first()
    )
