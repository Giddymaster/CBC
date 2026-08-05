"""The curriculum knowledge base that grounds generated content.

A `Document` is something authoritative a school works from — a KICD curriculum
design, an MoE circular, an approved course book, the school's own policy. It is
split into `Chunk`s, which are what retrieval actually searches and cites.

Two rules shape the model:

1. **Authority is a property of the source, not the document.** An MoE circular
   outranks a school handout on the same question, and retrieval orders by that.
   See `apps.schools.moe.AUTHORITY_RANK`.

2. **National documents are shared; school documents are not.** A KICD design is
   the same for every school, so `school` is null and every tenant can read it.
   A school's own upload sets `school` and stays inside that tenant.
"""

from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel
from apps.schools.moe import AUTHORITY_LABELS, authority_rank


class Source(TimeStampedModel):
    """Who published a document, and how much weight it carries."""

    class Authority(models.TextChoices):
        MOE = "MOE", AUTHORITY_LABELS["MOE"]
        KICD = "KICD", AUTHORITY_LABELS["KICD"]
        KNEC = "KNEC", AUTHORITY_LABELS["KNEC"]
        TSC = "TSC", AUTHORITY_LABELS["TSC"]
        COUNTY = "COUNTY", AUTHORITY_LABELS["COUNTY"]
        SCHOOL = "SCHOOL", AUTHORITY_LABELS["SCHOOL"]
        OTHER = "OTHER", AUTHORITY_LABELS["OTHER"]

    name = models.CharField(max_length=150)
    authority = models.CharField(
        max_length=10, choices=Authority.choices, default=Authority.OTHER
    )
    publisher = models.CharField(max_length=150, blank=True)
    url = models.URLField(blank=True)
    effective_date = models.DateField(
        null=True, blank=True, help_text="When this source took effect"
    )

    class Meta:
        ordering = ["-id"]

    @property
    def rank(self):
        return authority_rank(self.authority)

    def __str__(self):
        return f"{self.name} ({self.get_authority_display()})"


class Document(TimeStampedModel):
    class Kind(models.TextChoices):
        CURRICULUM_DESIGN = "DESIGN", "Curriculum design"
        POLICY = "POLICY", "Policy / circular"
        TEXTBOOK = "TEXTBOOK", "Approved course book"
        TEACHER_GUIDE = "GUIDE", "Teacher guide"
        ASSESSMENT_BANK = "BANK", "Assessment / question bank"
        OTHER = "OTHER", "Other"

    # Null school = national document, readable by every tenant.
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="documents",
        help_text="Leave blank for a national document shared by all schools",
    )
    source = models.ForeignKey(Source, on_delete=models.PROTECT, related_name="documents")
    title = models.CharField(max_length=250)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.OTHER)
    learning_area = models.ForeignKey(
        "assessments.LearningArea",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
        help_text="Leave blank if the document spans subjects",
    )
    grades = models.JSONField(
        default=list, blank=True, help_text="Grades it applies to, e.g. [7, 8, 9]"
    )
    file = models.FileField(upload_to="curriculum/%Y/", null=True, blank=True)
    text = models.TextField(
        blank=True, help_text="Extracted or pasted text — this is what gets indexed"
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents_uploaded",
    )
    indexed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["title", "id"]

    @property
    def is_national(self):
        return self.school_id is None

    @property
    def authority(self):
        return self.source.authority

    def covers_grade(self, grade):
        return not self.grades or grade in self.grades

    def __str__(self):
        return self.title


class Chunk(TimeStampedModel):
    """A retrievable passage. Small enough to cite, big enough to mean something."""

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    ordinal = models.PositiveIntegerField()
    heading = models.CharField(max_length=250, blank=True)
    text = models.TextField()
    # Lexical retrieval needs term counts; vector retrieval needs the embedding.
    # Both are optional so the base install works with neither service running.
    term_counts = models.JSONField(default=dict, blank=True)
    length = models.PositiveIntegerField(default=0)
    embedding = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["document_id", "ordinal"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "ordinal"], name="unique_chunk_ordinal"
            )
        ]

    def citation(self):
        parts = [self.document.title]
        if self.heading:
            parts.append(self.heading)
        return " — ".join(parts)

    def __str__(self):
        return f"{self.document_id}#{self.ordinal}"
