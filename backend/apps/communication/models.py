from django.conf import settings
from django.db import models

from apps.common.models import SchoolScopedModel


class Channel(models.TextChoices):
    SMS = "SMS", "SMS"
    WHATSAPP = "WHATSAPP", "WhatsApp"


class MessageBlast(SchoolScopedModel):
    """One thing the school wanted to tell a group of parents.

    Kept as its own record because a blast is a decision, not just traffic: who
    it went to, what it said, what it cost in messages, and who authorised it.
    The per-parent rows hang off it, so a failed delivery can be found and the
    school can answer "did the Grade 7 parents get the trip notice?".
    """

    class Audience(models.TextChoices):
        SCHOOL = "SCHOOL", "Every parent"
        GRADE = "GRADE", "One class"
        UNPAID = "UNPAID", "Parents with a fee balance"
        LEARNER = "LEARNER", "One learner's parents"

    title = models.CharField(max_length=120, blank=True)
    body = models.TextField(help_text="Supports {name} {learner} {class} {balance} {school}")
    channel = models.CharField(max_length=8, choices=Channel.choices, default=Channel.SMS)
    audience = models.CharField(max_length=8, choices=Audience.choices)
    grade = models.IntegerField(null=True, blank=True)
    stream = models.CharField(max_length=20, blank=True)
    learner = models.ForeignKey(
        "students.Learner", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="blasts",
    )
    recipients = models.PositiveIntegerField(default=0)
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="message_blasts",
    )

    class Meta:
        ordering = ["-created_at", "id"]

    def __str__(self):
        return f"{self.get_channel_display()} to {self.recipients} — {self.title or self.body[:40]}"


class SmsMessage(SchoolScopedModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SENT = "SENT", "Sent"
        FAILED = "FAILED", "Failed"
        STUBBED = "STUBBED", "Logged (no gateway configured)"

    recipient = models.CharField(max_length=15, help_text="MSISDN, e.g. 2547XXXXXXXX")
    body = models.TextField()
    channel = models.CharField(max_length=8, choices=Channel.choices, default=Channel.SMS)
    blast = models.ForeignKey(
        MessageBlast, on_delete=models.CASCADE, null=True, blank=True,
        related_name="messages",
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    provider_message_id = models.CharField(max_length=100, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at", "id"]

    def __str__(self):
        return f"{self.channel} to {self.recipient} [{self.status}]"


class Announcement(SchoolScopedModel):
    class Audience(models.TextChoices):
        ALL = "ALL", "Everyone"
        PARENTS = "PARENTS", "Parents"
        TEACHERS = "TEACHERS", "Teachers"

    title = models.CharField(max_length=200)
    body = models.TextField()
    audience = models.CharField(max_length=10, choices=Audience.choices, default=Audience.ALL)
    meeting_link = models.URLField(
        blank=True, help_text="Zoom/Meet deep-link — no embedded SDK needed"
    )
    send_sms = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at", "id"]

    def __str__(self):
        return self.title


class ParentMessage(SchoolScopedModel):
    """One note on a parent–staff thread about one learner."""

    learner = models.ForeignKey(
        "students.Learner", on_delete=models.CASCADE, related_name="parent_messages"
    )
    guardian = models.ForeignKey(
        "students.Guardian", on_delete=models.CASCADE, related_name="messages"
    )
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="parent_messages",
        help_text="The staff side of this thread",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_parent_messages"
    )
    body = models.TextField()
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "id"]

    @property
    def from_parent(self):
        return self.sender_id == self.guardian.user_id

    def __str__(self):
        return f"{self.learner} — {self.sender}"
