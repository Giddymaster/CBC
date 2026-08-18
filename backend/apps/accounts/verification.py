"""Issue and check one-time codes and links.

The engine behind phone/email verification, password reset and the login code.
A request mints a 6-digit OTP (for SMS) and a random link token (for email),
stores the code only as a hash, and sends it. A confirmation checks the hash in
constant time, honours the expiry and the attempt cap, and burns the record so
it can never be replayed.

SMS carries the digits; email carries a tap-to-verify link and the digits as a
fallback — one code, two ways to prove it.
"""

import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone

from apps.communication.email import send_email
from apps.communication.services import send_sms

from .models import Verification


def _otp():
    """A six-digit code, uniform across the whole range (leading zeros kept)."""
    return f"{secrets.randbelow(1_000_000):06d}"


def request_verification(*, channel, purpose, target, user=None, school=None):
    """Create a verification, send it, and return the record (never the code)."""
    code = _otp()
    record = Verification.objects.create(
        user=user,
        channel=channel,
        purpose=purpose,
        target=target,
        code_hash=make_password(code),
        token=secrets.token_urlsafe(32),
        expires_at=timezone.now() + timedelta(minutes=settings.OTP_TTL_MINUTES),
    )
    _deliver(record, code, school)
    return record


def _deliver(record, code, school):
    minutes = settings.OTP_TTL_MINUTES
    if record.channel == Verification.Channel.SMS:
        send_sms(
            school,
            record.target,
            f"Your ShuleNest code is {code}. It expires in {minutes} minutes. "
            f"Do not share it.",
        )
        return

    link = f"{settings.APP_BASE_URL}/verify/{record.token}"
    subject = _SUBJECTS.get(record.purpose, "Your ShuleNest code")
    send_email(
        record.target,
        subject,
        html=_email_html(subject, code, link, minutes),
        text=(
            f"{subject}\n\nYour code is {code} (expires in {minutes} minutes), "
            f"or open this link to continue:\n{link}\n\n"
            f"If you did not request this, ignore this email."
        ),
    )


_SUBJECTS = {
    Verification.Purpose.PASSWORD_RESET: "Reset your ShuleNest password",
    Verification.Purpose.EMAIL_VERIFY: "Verify your ShuleNest email",
    Verification.Purpose.LOGIN_2FA: "Your ShuleNest sign-in code",
}


def _email_html(subject, code, link, minutes):
    return f"""\
<div style="font-family:system-ui,Segoe UI,Arial,sans-serif;max-width:480px;margin:auto">
  <h2 style="color:#1a3a8f">ShuleNest</h2>
  <p>{subject}. Use this code, or tap the button below.</p>
  <p style="font-size:30px;font-weight:800;letter-spacing:4px;color:#1a3a8f">{code}</p>
  <p><a href="{link}" style="background:#2b6cb0;color:#fff;padding:10px 18px;
     border-radius:8px;text-decoration:none;font-weight:600">Continue</a></p>
  <p style="color:#718096;font-size:13px">This expires in {minutes} minutes. If you
     did not request it, you can ignore this email.</p>
</div>"""


class VerifyResult:
    OK = "OK"
    EXPIRED = "EXPIRED"
    TOO_MANY = "TOO_MANY"
    BAD_CODE = "BAD_CODE"
    NOT_FOUND = "NOT_FOUND"


def confirm_code(record, code):
    """Check a submitted OTP against a record. Consumes it on success; counts
    the try either way so guessing runs out."""
    if record is None:
        return VerifyResult.NOT_FOUND
    if record.consumed_at is not None:
        return VerifyResult.NOT_FOUND
    if record.expires_at <= timezone.now():
        return VerifyResult.EXPIRED
    if record.attempts >= settings.OTP_MAX_ATTEMPTS:
        return VerifyResult.TOO_MANY

    record.attempts += 1
    if check_password(str(code or "").strip(), record.code_hash):
        record.consumed_at = timezone.now()
        record.save(update_fields=["attempts", "consumed_at"])
        return VerifyResult.OK
    record.save(update_fields=["attempts"])
    return VerifyResult.BAD_CODE


def consume_token(token, *, purpose=None):
    """Resolve and burn an email magic-link token. Returns the record or None."""
    record = Verification.objects.filter(token=token, consumed_at__isnull=True).first()
    if record is None or record.expires_at <= timezone.now():
        return None
    if purpose is not None and record.purpose != purpose:
        return None
    record.consumed_at = timezone.now()
    record.save(update_fields=["consumed_at"])
    return record
