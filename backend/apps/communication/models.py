from django.db import models

from apps.common.models import SchoolScopedModel


class SmsMessage(SchoolScopedModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SENT = "SENT", "Sent"
        FAILED = "FAILED", "Failed"
        STUBBED = "STUBBED", "Logged (no gateway configured)"

    recipient = models.CharField(max_length=15, help_text="MSISDN, e.g. 2547XXXXXXXX")
    body = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    provider_message_id = models.CharField(max_length=100, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at", "id"]

    def __str__(self):
        return f"SMS to {self.recipient} [{self.status}]"


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
