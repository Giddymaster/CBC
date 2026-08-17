from django.db import models

from apps.common.models import SchoolScopedModel, TimeStampedModel

# The fee note's columns as most Kenyan schools head them. A school edits its
# own list on the School Profile page; this is only what a new school starts
# with, so nobody types ten headings before raising their first invoice.
DEFAULT_VOTE_HEADS = [
    "Tuition", "Activities", "Health", "Games", "Projects",
    "Exams", "Transport", "Lunch", "Development", "Boarding",
]


class School(TimeStampedModel):
    class Level(models.TextChoices):
        PRIMARY = "PRIMARY", "Primary"
        JUNIOR = "JSS", "Junior School"
        SENIOR = "SSS", "Senior School"

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
    # The school's handle in the URL — shulenest.com/<slug>/admin/... . Set once
    # from the name and kept stable, so a bookmarked link survives a rename.
    slug = models.SlugField(max_length=60, unique=True, blank=True)

    # The CBC levels this school offers — any combination of the three. A school
    # running primary through senior selects all three; most run one or two.
    # Replaces the old single-value field where "Composite" stood in for "more
    # than one".
    levels = models.JSONField(
        default=list,
        blank=True,
        help_text="Any of PRIMARY / JSS / SSS — the levels the school offers",
    )

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

    # How the operator reaches the school — its office line and email, kept
    # distinct from whoever currently holds the admin account (that person can
    # change; the school's own contact should not have to).
    contact_phone = models.CharField(max_length=15, blank=True)
    contact_email = models.EmailField(blank=True)

    # The school as it appears on paper. A report card, a fee note and an
    # admission form all go home in a child's bag, and a parent should be able
    # to tell at a glance whose letterhead they are holding and what number to
    # ring about it.
    alt_phone = models.CharField(max_length=15, blank=True)
    postal_address = models.CharField(max_length=120, blank=True)
    website = models.CharField(max_length=120, blank=True)
    motto = models.CharField(max_length=120, blank=True)
    logo = models.ImageField(upload_to="school_logos/", blank=True, null=True)

    # The fee note's columns, the school's own. Kept here rather than derived
    # from whatever amounts happen to be filled in, so a head the school added
    # survives an empty term instead of vanishing when nobody has priced it yet.
    vote_heads = models.JSONField(default=list, blank=True)

    paybill_account_prefix = models.CharField(
        max_length=10,
        blank=True,
        help_text="Prefix parents put before the admission number when paying via paybill",
    )

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._unique_slug()
        super().save(*args, **kwargs)

    def _unique_slug(self):
        """A URL handle from the name, made unique with a numeric suffix. Falls
        back to the code so a nameless or all-symbols school still gets one."""
        from django.utils.text import slugify

        base = slugify(self.name)[:50] or f"school-{self.code}".lower()
        candidate = base
        n = 2
        while School.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
            candidate = f"{base}-{n}"
            n += 1
        return candidate

    def __str__(self):
        return f"{self.name} ({self.code})"

    @classmethod
    def normalize_levels(cls, values):
        """Keep only known level codes, de-duplicated and in canonical order.

        Defensive on the way in: a legacy ``"COMPOSITE"`` expands to all three,
        and anything unrecognised is dropped rather than stored.
        """
        order = [code for code, _ in cls.Level.choices]
        chosen = set()
        for value in values or []:
            code = str(value).strip().upper()
            if code == "COMPOSITE":
                chosen.update(order)
            elif code in order:
                chosen.add(code)
        return [code for code in order if code in chosen]

    def fee_columns(self):
        """The vote heads to head the fee note with — the school's own if it
        has set them, otherwise the common Kenyan list to start from."""
        heads = [str(h).strip() for h in (self.vote_heads or []) if str(h).strip()]
        return heads or list(DEFAULT_VOTE_HEADS)


class SchoolDocument(SchoolScopedModel):
    """The school's own paperwork, filed where the office can find it.

    A school runs on documents it must produce on demand — the registration
    certificate when an inspector calls, the fee policy when a parent queries a
    balance, last year's board minutes. They currently live in a drawer or in
    somebody's WhatsApp; here they are filed by kind, with a date, and can be
    opened from any device the office signs in on.
    """

    class Category(models.TextChoices):
        REGISTRATION = "REGISTRATION", "Registration & licences"
        POLICY = "POLICY", "School policies"
        CIRCULAR = "CIRCULAR", "MoE circulars"
        BOARD = "BOARD", "Board & committee minutes"
        FINANCE = "FINANCE", "Finance & audit"
        SAFETY = "SAFETY", "Health & safety"
        TEMPLATE = "TEMPLATE", "Forms & templates"
        OTHER = "OTHER", "Other"

    title = models.CharField(max_length=200)
    category = models.CharField(
        max_length=14, choices=Category.choices, default=Category.OTHER
    )
    file = models.FileField(upload_to="school_documents/%Y/")
    note = models.TextField(blank=True)
    document_date = models.DateField(
        null=True, blank=True, help_text="The date on the document itself"
    )
    uploaded_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="school_documents",
    )

    class Meta:
        ordering = ["category", "-document_date", "-created_at", "id"]

    def __str__(self):
        return f"{self.title} ({self.get_category_display()})"
