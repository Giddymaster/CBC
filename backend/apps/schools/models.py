from django.db import models

from apps.common.models import TimeStampedModel


class School(TimeStampedModel):
    class Level(models.TextChoices):
        PRIMARY = "PRIMARY", "Primary"
        JUNIOR = "JSS", "Junior School"
        SENIOR = "SSS", "Senior School"
        COMPOSITE = "COMPOSITE", "Composite"

    name = models.CharField(max_length=200)
    code = models.CharField(max_length=30, unique=True, help_text="MoE school code")
    kemis_code = models.CharField(max_length=30, blank=True)
    level = models.CharField(max_length=10, choices=Level.choices, default=Level.JUNIOR)
    county = models.CharField(max_length=50)
    subcounty = models.CharField(max_length=50, blank=True)
    paybill_account_prefix = models.CharField(
        max_length=10,
        blank=True,
        help_text="Prefix parents put before the admission number when paying via paybill",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"
