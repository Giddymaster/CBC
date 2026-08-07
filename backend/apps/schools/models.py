from django.db import models

from apps.common.models import TimeStampedModel


class School(TimeStampedModel):
    class Level(models.TextChoices):
        PRIMARY = "PRIMARY", "Primary"
        JUNIOR = "JSS", "Junior School"
        SENIOR = "SSS", "Senior School"
        COMPOSITE = "COMPOSITE", "Composite"

    # How the Ministry of Education classifies a school. `category` is the
    # placement tier used from Junior School into Senior School — a school is
    # gazetted as one of these four, and it governs which learners it draws.
    class Category(models.TextChoices):
        NATIONAL = "NATIONAL", "National"
        EXTRA_COUNTY = "EXTRA_COUNTY", "Extra-County"
        COUNTY = "COUNTY", "County"
        SUB_COUNTY = "SUB_COUNTY", "Sub-County"

    class Gender(models.TextChoices):
        MIXED = "MIXED", "Mixed"
        BOYS = "BOYS", "Boys"
        GIRLS = "GIRLS", "Girls"

    class Accommodation(models.TextChoices):
        DAY = "DAY", "Day"
        BOARDING = "BOARDING", "Boarding"
        DAY_BOARDING = "DAY_BOARDING", "Day & Boarding"

    class Ownership(models.TextChoices):
        PUBLIC = "PUBLIC", "Public"
        PRIVATE = "PRIVATE", "Private"
        FAITH = "FAITH", "Faith-based / Sponsored"

    name = models.CharField(max_length=200)
    code = models.CharField(max_length=30, unique=True, help_text="MoE school code")
    kemis_code = models.CharField(max_length=30, blank=True)
    level = models.CharField(max_length=10, choices=Level.choices, default=Level.JUNIOR)

    # Where it sits, county down to the education zone. County and sub-county
    # match KEMIS; ward is the electoral unit; zone is the education office's
    # own subdivision.
    county = models.CharField(max_length=50)
    subcounty = models.CharField(max_length=50, blank=True)
    ward = models.CharField(max_length=60, blank=True)
    zone = models.CharField(
        max_length=60, blank=True, help_text="Education zone / administrative location"
    )

    # MoE classification — all optional, since a young primary school may not
    # carry a placement category.
    category = models.CharField(
        max_length=12, choices=Category.choices, blank=True,
        help_text="MoE placement tier (national / extra-county / county / sub-county)",
    )
    gender = models.CharField(max_length=6, choices=Gender.choices, blank=True)
    accommodation = models.CharField(
        max_length=12, choices=Accommodation.choices, blank=True
    )
    ownership = models.CharField(max_length=8, choices=Ownership.choices, blank=True)

    paybill_account_prefix = models.CharField(
        max_length=10,
        blank=True,
        help_text="Prefix parents put before the admission number when paying via paybill",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"
