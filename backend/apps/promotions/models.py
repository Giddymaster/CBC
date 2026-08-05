"""Moving a whole school up a year.

This is the most destructive operation the system offers — one mistake
rearranges every register in the school — so it is built in three deliberate
steps rather than one button:

1. **Preview.** A run is created with one outcome row per learner, each showing
   where they are and where they would go. Nothing has changed yet.
2. **Review.** The head adjusts individual learners: hold one back, mark another
   as transferred out, confirm a Senior School pathway.
3. **Apply.** The run is committed, and every outcome records the learner's
   state *before* the change so the whole run can be reversed exactly.

Reversal matters more than it looks. Promotion happens in the holidays, and the
error is usually noticed after the fact.
"""

from django.conf import settings
from django.db import models

from apps.common.models import SchoolScopedModel


class AcademicYear(SchoolScopedModel):
    """The school's own calendar. Gives "which year are we in" a home, so
    promotion is not driven by the server clock."""

    year = models.PositiveSmallIntegerField()
    starts_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)
    is_current = models.BooleanField(default=False)

    class Meta:
        ordering = ["-year"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "year"], name="one_academic_year_per_school"
            ),
            # Exactly one year can be the current one.
            models.UniqueConstraint(
                fields=["school"],
                condition=models.Q(is_current=True),
                name="one_current_academic_year",
            ),
        ]

    def __str__(self):
        return f"{self.year}{' (current)' if self.is_current else ''}"


class PromotionRun(SchoolScopedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft — previewed, not applied"
        APPLIED = "APPLIED", "Applied"
        REVERSED = "REVERSED", "Reversed"

    from_year = models.PositiveSmallIntegerField()
    to_year = models.PositiveSmallIntegerField()
    grade = models.IntegerField(
        null=True, blank=True, help_text="Limit to one grade; blank = whole school"
    )
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.DRAFT)
    note = models.CharField(max_length=200, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="promotion_runs_created",
    )
    applied_at = models.DateTimeField(null=True, blank=True)
    applied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="promotion_runs_applied",
    )
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="promotion_runs_reversed",
    )

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_editable(self):
        return self.status == self.Status.DRAFT

    def __str__(self):
        return f"{self.from_year} → {self.to_year} ({self.get_status_display()})"


class PromotionOutcome(SchoolScopedModel):
    """What happens to one learner in a run, and what they were before."""

    class Action(models.TextChoices):
        PROMOTE = "PROMOTE", "Move up a grade"
        REPEAT = "REPEAT", "Repeat the year"
        TRANSFER_OUT = "TRANSFER", "Transferred to another school"
        GRADUATE = "GRADUATE", "Completed Grade 12"

    run = models.ForeignKey(
        PromotionRun, on_delete=models.CASCADE, related_name="outcomes"
    )
    learner = models.ForeignKey(
        "students.Learner", on_delete=models.CASCADE, related_name="promotion_outcomes"
    )
    action = models.CharField(
        max_length=8, choices=Action.choices, default=Action.PROMOTE
    )
    to_grade = models.IntegerField(null=True, blank=True)
    to_stream = models.CharField(max_length=20, blank=True)
    pathway = models.ForeignKey(
        "students.Pathway", on_delete=models.SET_NULL, null=True, blank=True,
        help_text="Senior School pathway, set at the Grade 9 to 10 transition",
    )
    pathway_track = models.CharField(max_length=60, blank=True)
    # Why the system suggested this pathway — shown to the head, never applied
    # on its own.
    pathway_rationale = models.JSONField(default=dict, blank=True)
    note = models.CharField(max_length=200, blank=True)

    # State before applying, so a reversal restores exactly what was there.
    previous_grade = models.IntegerField(null=True, blank=True)
    previous_stream = models.CharField(max_length=20, blank=True)
    previous_pathway = models.ForeignKey(
        "students.Pathway", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )
    previous_status = models.CharField(max_length=12, blank=True)
    previous_active = models.BooleanField(null=True, blank=True)
    applied = models.BooleanField(default=False)

    class Meta:
        ordering = ["learner__grade", "learner__admission_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["run", "learner"], name="one_outcome_per_learner_per_run"
            )
        ]

    def __str__(self):
        return f"{self.learner} — {self.get_action_display()}"
