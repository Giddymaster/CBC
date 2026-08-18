from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.common.models import TimeStampedModel


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "School Admin"
        TEACHER = "TEACHER", "Teacher"
        SUPPORT = "SUPPORT", "Support staff"
        PARENT = "PARENT", "Parent/Guardian"

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.TEACHER)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
    )
    phone = models.CharField(max_length=15, blank=True, help_text="MSISDN, e.g. 2547XXXXXXXX")
    # An admin-generated password is a shared secret: the admin typed it, read
    # it aloud, and probably wrote it on a note. It is a handover credential,
    # not the staff member's own, so the app makes them replace it before they
    # can do anything else.
    must_change_password = models.BooleanField(
        default=False,
        help_text="Set when an admin issues a password; cleared once the user picks their own",
    )
    password_changed_at = models.DateTimeField(null=True, blank=True)
    phone_verified = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)
    # Opt-in second factor: with this set, a correct password only earns a
    # one-time code sent to a verified contact; the token comes after the code.
    two_factor_enabled = models.BooleanField(default=False)


class Verification(TimeStampedModel):
    """A one-time proof that someone holds a phone or an email.

    One record, three jobs — verifying a new contact, resetting a password, a
    login second factor — because they are the same shape: send a secret to a
    channel, then check what comes back. The secret is stored only as a hash, so
    a leaked database row cannot be replayed; a random token backs the email
    magic-link. Codes expire and are single-use, with a hard cap on guesses.
    """

    class Channel(models.TextChoices):
        SMS = "SMS", "SMS"
        EMAIL = "EMAIL", "Email"

    class Purpose(models.TextChoices):
        PHONE_VERIFY = "PHONE_VERIFY", "Verify phone"
        EMAIL_VERIFY = "EMAIL_VERIFY", "Verify email"
        PASSWORD_RESET = "PASSWORD_RESET", "Password reset"
        LOGIN_2FA = "LOGIN_2FA", "Login code"

    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, null=True, blank=True,
        related_name="verifications",
    )
    channel = models.CharField(max_length=8, choices=Channel.choices)
    purpose = models.CharField(max_length=16, choices=Purpose.choices)
    target = models.CharField(max_length=120, help_text="The phone or email it was sent to")
    code_hash = models.CharField(max_length=256, blank=True)
    token = models.CharField(max_length=64, unique=True, db_index=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-created_at", "id"]
        indexes = [models.Index(fields=["purpose", "target"])]

    @property
    def is_live(self):
        from django.utils import timezone

        return self.consumed_at is None and self.expires_at > timezone.now()

    def __str__(self):
        return f"{self.get_purpose_display()} to {self.target} [{self.channel}]"
