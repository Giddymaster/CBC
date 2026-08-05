from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SchoolScopedModel(TimeStampedModel):
    """Row-based multi-tenancy: every tenant-owned row carries its school.

    All API access goes through SchoolScopedViewSet, which filters by the
    requesting user's school — a user can never read or write another
    school's rows.
    """

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="%(class)ss"
    )

    class Meta:
        abstract = True


class IdempotentRequest(models.Model):
    """Stored first-response for offline-tolerant write endpoints.

    Clients on flaky connections retry with the same Idempotency-Key header;
    a replay returns the stored response instead of duplicating the write.
    """

    key = models.CharField(max_length=128, unique=True)
    method = models.CharField(max_length=8)
    path = models.CharField(max_length=255)
    status_code = models.PositiveSmallIntegerField()
    response_body = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.method} {self.path} [{self.key}]"
