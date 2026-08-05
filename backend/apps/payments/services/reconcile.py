"""Match incoming M-Pesa credits to invoices and apply them atomically."""

from decimal import Decimal

from django.db import IntegrityError, transaction

from apps.students.models import Learner

from ..models import Invoice, MpesaTransaction


def record_transaction(
    *, school, source, receipt, phone, amount, account_reference="", invoice=None, raw=None
) -> MpesaTransaction | None:
    """Create the transaction and credit an invoice. Returns None if this
    receipt was already processed (replayed callback) — the invoice is NOT
    credited twice."""
    amount = Decimal(str(amount))

    if invoice is None and account_reference:
        # C2B: parents key in the admission number as the account reference.
        ref = account_reference.strip().upper()
        if school.paybill_account_prefix and ref.startswith(school.paybill_account_prefix.upper()):
            ref = ref[len(school.paybill_account_prefix):]
        learner = Learner.objects.filter(school=school, admission_number__iexact=ref).first()
        if learner:
            invoice = (
                learner.invoices.exclude(status=Invoice.Status.PAID)
                .order_by("created_at")
                .first()
            )

    try:
        with transaction.atomic():
            txn = MpesaTransaction.objects.create(
                school=school,
                source=source,
                mpesa_receipt=receipt,
                phone=phone,
                amount=amount,
                account_reference=account_reference,
                invoice=invoice,
                raw_payload=raw or {},
            )
            if invoice:
                invoice.apply_payment(amount)
    except IntegrityError:
        # Duplicate receipt => replayed callback. Idempotent no-op.
        return None

    from apps.common.audit import record as audit

    audit(
        actor=None,  # a webhook has no signed-in user
        school=school,
        action="PAYMENT_RECORDED",
        target=txn,
        label=f"{receipt} - KES {amount}",
        detail={
            "source": source,
            "reference": account_reference,
            "invoice": invoice.id if invoice else None,
            "matched": bool(invoice),
        },
    )
    return txn
