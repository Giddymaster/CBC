"""Who changed what.

A system holding minors' records needs to be able to answer "who moved this
child's mark from 34 to 74, and when". `updated_at` cannot answer it.

Deliberately **explicit, not signal-driven**. A `post_save` hook on every model
would log migrations, seed data and every incidental touch, and the useful
entries would drown. Instead `record()` is called at the decisions a school
would ask about later: a mark corrected, a learner deactivated, a report
approved, a promotion applied, admission rights granted, a password reset.

Entries are **append-only**. The API offers no create, update or delete — a log
an admin can edit is not evidence of anything.
"""

from django.conf import settings
from django.db import models

from .models import TimeStampedModel


class AuditEntry(TimeStampedModel):
    """One recorded action. Never edited after it is written."""

    class Action(models.TextChoices):
        SCORE_CHANGED = "SCORE_CHANGED", "Mark changed"
        LEARNER_DEACTIVATED = "LEARNER_DEACTIVATED", "Learner deactivated"
        LEARNER_REACTIVATED = "LEARNER_REACTIVATED", "Learner reactivated"
        LEARNER_ADMITTED = "LEARNER_ADMITTED", "Learner admitted"
        LEARNERS_IMPORTED = "LEARNERS_IMPORTED", "Learners imported"
        STAFF_DEACTIVATED = "STAFF_DEACTIVATED", "Staff deactivated"
        STAFF_ADDED = "STAFF_ADDED", "Staff added"
        REPORT_REVIEWED = "REPORT_REVIEWED", "Staff report reviewed"
        SCHEME_REVIEWED = "SCHEME_REVIEWED", "Scheme of work reviewed"
        PROMOTION_APPLIED = "PROMOTION_APPLIED", "Promotion applied"
        PROMOTION_REVERSED = "PROMOTION_REVERSED", "Promotion reversed"
        RIGHTS_GRANTED = "RIGHTS_GRANTED", "Admission rights granted"
        RIGHTS_WITHDRAWN = "RIGHTS_WITHDRAWN", "Admission rights withdrawn"
        PASSWORD_RESET = "PASSWORD_RESET", "Password reset by admin"
        PAYMENT_RECORDED = "PAYMENT_RECORDED", "Payment recorded"
        SCHOOL_PROVISIONED = "SCHOOL_PROVISIONED", "School provisioned"
        SUBSCRIPTION_INVOICED = "SUBSCRIPTION_INVOICED", "Subscription invoiced"
        SUBSCRIPTION_PAID = "SUBSCRIPTION_PAID", "Subscription paid"
        SUBSCRIPTION_STATUS = "SUBSCRIPTION_STATUS", "Subscription status changed"

    # Null school only for platform-level actions; everything else is scoped.
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="audit_entries",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_entries",
    )
    # Kept as text so the entry survives the actor being deleted.
    actor_name = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=24, choices=Action.choices)
    target_type = models.CharField(max_length=50, blank=True)
    target_id = models.CharField(max_length=40, blank=True)
    # What the row was about, in words — an id alone is unreadable a year later.
    label = models.CharField(max_length=200, blank=True)
    detail = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["school", "-created_at"]),
            models.Index(fields=["action"]),
        ]
        verbose_name_plural = "audit entries"

    def __str__(self):
        return f"{self.actor_name} {self.action} {self.label}".strip()


def record(*, actor, school, action, target=None, label="", detail=None):
    """Write one entry. Never raises into the caller.

    An audit write must not be able to fail the thing it is describing — a
    school that cannot save a mark because logging broke is worse off than one
    with a gap in its log. Failures are swallowed deliberately.
    """
    try:
        return AuditEntry.objects.create(
            school=school,
            actor=actor if getattr(actor, "pk", None) else None,
            actor_name=(
                (actor.get_full_name() or actor.username) if getattr(actor, "pk", None)
                else "system"
            ),
            action=action,
            target_type=target.__class__.__name__ if target is not None else "",
            target_id=str(getattr(target, "pk", "") or ""),
            label=label[:200],
            detail=detail or {},
        )
    except Exception:
        return None
