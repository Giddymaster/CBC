"""The control plane: plans, subscriptions, invoices, and operator announcements.

None of these are `SchoolScopedModel`. They are *about* schools, not owned by
one — they live above the tenant boundary, and only the operator touches them.
A school admin may read their own school's subscription and invoices; that is
all the tenant plane is allowed to see of the control plane.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.models import TimeStampedModel


class Plan(TimeStampedModel):
    """What a school is charged. Billed per active learner, per term.

    A `minimum_charge` floor keeps a very small school from paying almost
    nothing while still costing you to serve.
    """

    name = models.CharField(max_length=100)
    price_per_learner = models.DecimalField(
        max_digits=8, decimal_places=2,
        help_text="Charge per active learner, per term (KES)",
    )
    minimum_charge = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0"),
        help_text="Floor for a term's bill, however few learners",
    )
    currency = models.CharField(max_length=3, default="KES")
    trial_days = models.PositiveSmallIntegerField(
        default=30, help_text="Free-trial length for a newly provisioned school"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["price_per_learner", "id"]

    def quote(self, learner_count):
        return max(
            Decimal(learner_count) * self.price_per_learner, self.minimum_charge
        )

    def __str__(self):
        return f"{self.name} — KES {self.price_per_learner}/learner/term"


class Subscription(TimeStampedModel):
    """One per school. The lever that turns access on and off.

    `status` is the operator-set base (trial / active / cancelled). The *effective*
    access state is computed from dates on every read, so no scheduled job is
    needed to move a school into read-only when its term lapses — the answer is
    always current when asked.
    """

    class Status(models.TextChoices):
        TRIAL = "TRIAL", "Trial"
        ACTIVE = "ACTIVE", "Active"
        CANCELLED = "CANCELLED", "Cancelled"

    # Effective access states (derived, not stored).
    TRIAL_STATE = "TRIAL"
    ACTIVE_STATE = "ACTIVE"
    GRACE_STATE = "GRACE"          # term lapsed, within grace — still writable
    READ_ONLY_STATE = "READ_ONLY"  # grace elapsed — read but not write
    CANCELLED_STATE = "CANCELLED"  # off-boarded — read but not write

    school = models.OneToOneField(
        "schools.School", on_delete=models.CASCADE, related_name="subscription"
    )
    plan = models.ForeignKey(
        Plan, on_delete=models.PROTECT, related_name="subscriptions"
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.TRIAL
    )
    trial_ends_on = models.DateField(null=True, blank=True)
    # End date of the last term paid for. Full access up to here, then grace.
    paid_through = models.DateField(null=True, blank=True)
    grace_days = models.PositiveSmallIntegerField(default=14)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="subscriptions_created",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["school__name"]

    # --- The access decision, in one place ---------------------------------
    def effective_state(self, today=None):
        today = today or timezone.localdate()
        if self.status == self.Status.CANCELLED:
            return self.CANCELLED_STATE
        if self.status == self.Status.TRIAL and (
            self.trial_ends_on is None or today <= self.trial_ends_on
        ):
            return self.TRIAL_STATE
        if self.paid_through and today <= self.paid_through:
            return self.ACTIVE_STATE
        if self.paid_through and today <= self.paid_through + timezone.timedelta(
            days=self.grace_days
        ):
            return self.GRACE_STATE
        return self.READ_ONLY_STATE

    def can_write(self, today=None):
        return self.effective_state(today) in (
            self.TRIAL_STATE, self.ACTIVE_STATE, self.GRACE_STATE
        )

    def days_left(self, today=None):
        """Days of full access remaining, for the reminder banner."""
        today = today or timezone.localdate()
        horizon = self.paid_through or self.trial_ends_on
        return (horizon - today).days if horizon else None

    def __str__(self):
        return f"{self.school.name} — {self.effective_state()}"


class SubscriptionInvoice(TimeStampedModel):
    """A bill for one term. Amount is a snapshot: the learner count and unit
    price at the moment of issue, so a later change to either does not rewrite
    history."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SENT = "SENT", "Sent"
        PAID = "PAID", "Paid"
        VOID = "VOID", "Void"

    subscription = models.ForeignKey(
        Subscription, on_delete=models.CASCADE, related_name="invoices"
    )
    period_label = models.CharField(max_length=60, help_text="e.g. Term 2 2026")
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(
        help_text="Access is paid through this date once the invoice is paid"
    )
    learner_count = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)
    minimum_charge = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="KES")

    status = models.CharField(max_length=6, choices=Status.choices, default=Status.SENT)
    issued_on = models.DateField(default=timezone.localdate)
    due_on = models.DateField(null=True, blank=True)
    paid_on = models.DateField(null=True, blank=True)
    payment_reference = models.CharField(
        max_length=100, blank=True, help_text="M-Pesa code, bank ref, cheque no…"
    )
    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="invoices_marked",
    )

    class Meta:
        ordering = ["-issued_on", "-id"]

    def is_overdue(self, today=None):
        today = today or timezone.localdate()
        return self.status == self.Status.SENT and self.due_on and self.due_on < today

    def __str__(self):
        return f"{self.subscription.school.name} — {self.period_label}: KES {self.amount}"


class PlatformAnnouncement(TimeStampedModel):
    """Operator → school admins: releases, maintenance windows, billing notices.

    Distinct from the in-school announcements, which a school sends its own
    parents and teachers. This one is you, talking to every school's office.
    """

    class Category(models.TextChoices):
        FEATURE = "FEATURE", "New feature"
        UPDATE = "UPDATE", "Update"
        MAINTENANCE = "MAINTENANCE", "Maintenance"
        BILLING = "BILLING", "Billing"
        OTHER = "OTHER", "Notice"

    title = models.CharField(max_length=200)
    body = models.TextField()
    category = models.CharField(
        max_length=12, choices=Category.choices, default=Category.UPDATE
    )
    link = models.URLField(blank=True, help_text="Optional 'read more' link")
    published = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="platform_announcements",
    )

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return self.title


class AnnouncementReceipt(TimeStampedModel):
    """Which admin has seen which platform announcement, so the banner clears."""

    announcement = models.ForeignKey(
        PlatformAnnouncement, on_delete=models.CASCADE, related_name="receipts"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="announcement_receipts"
    )
    seen_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["announcement", "user"], name="one_receipt_per_admin"
            )
        ]
