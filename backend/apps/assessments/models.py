from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.common.models import SchoolScopedModel, TimeStampedModel


class CompetencyLevel(models.TextChoices):
    """CBC performance levels."""

    EE = "EE", "Exceeding Expectation"
    ME = "ME", "Meeting Expectation"
    AE = "AE", "Approaching Expectation"
    BE = "BE", "Below Expectation"


def derive_competency_level(percent: float) -> str:
    """Default CBC rubric bands. Schools can override per-assessment via
    Assessment.rubric (list of [min_percent, level] pairs, highest first)."""
    if percent >= 80:
        return CompetencyLevel.EE
    if percent >= 60:
        return CompetencyLevel.ME
    if percent >= 40:
        return CompetencyLevel.AE
    return CompetencyLevel.BE


class LearningArea(TimeStampedModel):
    """Subject / learning area (national, not school-scoped)."""

    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True)
    grades = models.JSONField(default=list, help_text="Grades where offered, e.g. [7, 8, 9]")
    pathway = models.ForeignKey(
        "students.Pathway",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Set for Senior School pathway-specific areas",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Assessment(SchoolScopedModel):
    class Kind(models.TextChoices):
        CAT1 = "CAT1", "CAT 1"
        CAT2 = "CAT2", "CAT 2"
        RAT = "RAT", "RAT"
        MIDTERM = "MIDTERM", "Midterm Exam"
        ENDTERM = "ENDTERM", "Final Exam"
        FORMATIVE = "FORMATIVE", "Formative/Classroom Assessment"

    kind = models.CharField(max_length=10, choices=Kind.choices)
    learning_area = models.ForeignKey(LearningArea, on_delete=models.CASCADE)
    grade = models.IntegerField()
    stream = models.CharField(max_length=20, blank=True)
    term = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(3)])
    year = models.PositiveSmallIntegerField()
    max_marks = models.PositiveSmallIntegerField(default=100)
    date = models.DateField(null=True, blank=True)
    rubric = models.JSONField(
        default=list,
        blank=True,
        help_text='Optional override bands, e.g. [[80, "EE"], [60, "ME"], [40, "AE"], [0, "BE"]]',
    )

    class Meta:
        ordering = ["-year", "-term", "grade", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "kind", "learning_area", "grade", "stream", "term", "year"],
                name="unique_assessment_slot",
            )
        ]

    def level_for(self, marks: float) -> str:
        percent = (marks / self.max_marks) * 100 if self.max_marks else 0
        for band_min, level in self.rubric or []:
            if percent >= band_min:
                return level
        if self.rubric:
            return CompetencyLevel.BE
        return derive_competency_level(percent)

    def __str__(self):
        return f"{self.get_kind_display()} {self.learning_area} G{self.grade} T{self.term} {self.year}"


class Score(SchoolScopedModel):
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name="scores")
    learner = models.ForeignKey("students.Learner", on_delete=models.CASCADE, related_name="scores")
    marks = models.DecimalField(max_digits=6, decimal_places=2)
    competency_level = models.CharField(
        max_length=2, choices=CompetencyLevel.choices, editable=False
    )
    comment = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["learner_id", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["assessment", "learner"], name="one_score_per_learner_per_assessment"
            )
        ]

    def save(self, *args, **kwargs):
        self.competency_level = self.assessment.level_for(float(self.marks))
        # update_or_create() saves with an explicit update_fields list. Without
        # this, a corrected mark would be stored while the learner kept the
        # competency level derived from the *old* mark — a wrong report card.
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            kwargs["update_fields"] = {*update_fields, "competency_level", "updated_at"}
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.learner} {self.assessment}: {self.marks} ({self.competency_level})"
