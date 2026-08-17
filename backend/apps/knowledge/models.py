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


def youtube_id(url):
    """Pull the 11-character video id out of any shape of YouTube link.

    Handles watch?v=, youtu.be/, /embed/, /shorts/ and a bare id. Returns "" if
    there is nothing that looks like one, so a mistyped link fails visibly
    rather than embedding a broken player.
    """
    import re

    if not url:
        return ""
    text = url.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", text):
        return text
    patterns = [
        r"(?:v=|/embed/|/shorts/|youtu\.be/)([A-Za-z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return ""


class LearningResource(TimeStampedModel):
    """Something a learner watches, reads or works through.

    The curriculum `Document` grounds what the school *produces* — schemes,
    reports — and is staff-facing. A LearningResource is the other direction:
    material a learner or parent *consumes*, a KICD-aligned video, an approved
    course book, a past paper, a simulation. Same two rules as Document, so the
    two libraries behave alike: authority comes from the source, and a national
    resource (school null) is shared by every tenant while a school's own stays
    inside it.

    Discovery runs on the same retrieval engine as the curriculum base
    (apps.knowledge.retrieval.search_resources), so "photosynthesis grade 7"
    surfaces the right video and book together.
    """

    class Kind(models.TextChoices):
        VIDEO = "VIDEO", "Video lesson"
        BOOK = "BOOK", "Book / textbook"
        NOTES = "NOTES", "Notes / revision"
        PAPER = "PAPER", "Past paper / quiz"
        SIMULATION = "SIMULATION", "Simulation / interactive"
        LINK = "LINK", "Web resource"

    # Null school = a national resource every school sees.
    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, null=True, blank=True,
        related_name="learning_resources",
        help_text="Leave blank for a national resource shared by all schools",
    )
    source = models.ForeignKey(
        Source, on_delete=models.PROTECT, related_name="learning_resources",
        null=True, blank=True,
    )
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.VIDEO)
    title = models.CharField(max_length=250)
    description = models.TextField(blank=True)
    topic = models.CharField(
        max_length=200, blank=True, help_text="Strand / sub-strand or topic, for search"
    )
    learning_area = models.ForeignKey(
        "assessments.LearningArea", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="learning_resources",
    )
    grades = models.JSONField(default=list, blank=True, help_text="Grades it suits, e.g. [7, 8]")

    # A resource is either a link (video / web / online book) or an uploaded
    # file (a PDF book, notes, a past paper). One of url / file is set.
    url = models.URLField(blank=True, help_text="YouTube link, or a link to a book/resource")
    file = models.FileField(upload_to="elearning/%Y/", null=True, blank=True)

    author = models.CharField(max_length=150, blank=True)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="learning_resources_added",
    )

    class Meta:
        ordering = ["learning_area__name", "title", "id"]

    @property
    def is_national(self):
        return self.school_id is None

    @property
    def youtube_id(self):
        return youtube_id(self.url) if self.kind == self.Kind.VIDEO else ""

    def covers_grade(self, grade):
        return not self.grades or grade in self.grades

    def search_text(self):
        parts = [self.title, self.topic, self.description]
        if self.learning_area_id:
            parts.append(self.learning_area.name)
        return " ".join(p for p in parts if p)

    def __str__(self):
        return f"{self.title} ({self.get_kind_display()})"


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
