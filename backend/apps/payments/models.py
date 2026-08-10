from decimal import Decimal

from django.db import models

from apps.common.models import SchoolScopedModel

# The vote heads a Kenyan school's fee structure is broken into. Schools add
# their own; these are the columns the grid starts with.
DEFAULT_VOTE_HEADS = [
    "Tuition", "Activities", "Health", "Games", "Projects",
    "Exams", "Transport", "Lunch", "Development", "Boarding",
]


class FeeStructure(SchoolScopedModel):
    grade = models.IntegerField()
    term = models.PositiveSmallIntegerField()
    year = models.PositiveSmallIntegerField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    # What the total is made of: {"Tuition": "6000", "Games": "500", ...}.
    # A fee note has to itemise — parents and the board both ask "for what?"
    breakdown = models.JSONField(default=dict, blank=True)
    description = models.CharField(max_length=200, blank=True)

    def total_from_breakdown(self):
        from decimal import InvalidOperation

        total = Decimal("0")
        for value in (self.breakdown or {}).values():
            try:
                total += Decimal(str(value or 0))
            except InvalidOperation:
                continue
        return total

    class Meta:
        ordering = ["-year", "-term", "grade"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "grade", "term", "year"], name="one_fee_structure_per_slot"
            )
        ]

    def __str__(self):
        return f"G{self.grade} T{self.term} {self.year}: KES {self.amount}"


class Invoice(SchoolScopedModel):
    class Status(models.TextChoices):
        UNPAID = "UNPAID", "Unpaid"
        PARTIAL = "PARTIAL", "Partially Paid"
        PAID = "PAID", "Paid"

    learner = models.ForeignKey(
        "students.Learner", on_delete=models.CASCADE, related_name="invoices"
    )
    fee_structure = models.ForeignKey(FeeStructure, on_delete=models.PROTECT)
    amount_due = models.DecimalField(max_digits=10, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.UNPAID)

    def apply_payment(self, amount: Decimal):
        self.amount_paid += amount
        self.refresh_status()

    def refresh_status(self):
        if self.amount_paid >= self.amount_due:
            self.status = self.Status.PAID
        elif self.amount_paid > 0:
            self.status = self.Status.PARTIAL
        else:
            self.status = self.Status.UNPAID
        self.save()

    @property
    def balance(self):
        return self.amount_due - self.amount_paid

    class Meta:
        ordering = ["-created_at", "id"]

    def __str__(self):
        return f"Invoice {self.pk} {self.learner} [{self.status}]"


class Payment(SchoolScopedModel):
    """One instalment against an invoice.

    Families do not pay in one lump on one day: a parent pays 3,000 in cash at
    the gate in May, 5,000 by M-Pesa in June, and the balance by bank slip in
    August. Each of those is a row here — its own amount, date, method and
    reference — and the invoice's paid total is the sum of them. Without this
    the register could only ever say "partially paid" without saying when, how
    much, or how.
    """

    class Method(models.TextChoices):
        CASH = "CASH", "Cash"
        MPESA = "MPESA", "M-Pesa"
        BANK = "BANK", "Bank deposit"
        CHEQUE = "CHEQUE", "Cheque"
        BURSARY = "BURSARY", "Bursary / sponsor"
        WAIVER = "WAIVER", "Waiver"

    invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE, related_name="payments"
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(max_length=8, choices=Method.choices, default=Method.CASH)
    reference = models.CharField(
        max_length=60, blank=True, help_text="M-Pesa code, bank slip or receipt no"
    )
    paid_on = models.DateField(help_text="The day the family actually paid")
    note = models.CharField(max_length=200, blank=True)
    received_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="payments_received",
    )

    class Meta:
        ordering = ["-paid_on", "-id"]

    def __str__(self):
        return f"KES {self.amount} {self.get_method_display()} on {self.paid_on}"


class MpesaTransaction(SchoolScopedModel):
    """Every M-Pesa credit we hear about — from STK callbacks or C2B paybill
    confirmations. Idempotent on receipt number: a replayed callback can
    never double-credit an invoice."""

    class Source(models.TextChoices):
        STK = "STK", "STK Push"
        C2B = "C2B", "C2B Paybill"

    source = models.CharField(max_length=3, choices=Source.choices)
    mpesa_receipt = models.CharField(max_length=30, unique=True)
    phone = models.CharField(max_length=15)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    account_reference = models.CharField(
        max_length=30, blank=True, help_text="Learner admission number the parent keyed in"
    )
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
        help_text="Null = unmatched, queued for manual reconciliation",
    )
    raw_payload = models.JSONField(default=dict)

    class Meta:
        ordering = ["-created_at", "id"]

    def __str__(self):
        return f"{self.mpesa_receipt} KES {self.amount} ({self.source})"


class StkPushRequest(SchoolScopedModel):
    """Outbound STK Push attempts, keyed by CheckoutRequestID for callback matching."""

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="stk_requests")
    phone = models.CharField(max_length=15)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    checkout_request_id = models.CharField(max_length=100, blank=True, unique=True, null=True)
    merchant_request_id = models.CharField(max_length=100, blank=True)
    succeeded = models.BooleanField(null=True, blank=True, help_text="Null until callback arrives")
    result_description = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at", "id"]

    def __str__(self):
        return f"STK {self.checkout_request_id or '(pending)'} -> invoice {self.invoice_id}"
