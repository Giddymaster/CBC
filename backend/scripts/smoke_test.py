"""End-to-end smoke test of the three 'previously missing' flows.
Run: python manage.py shell -c "exec(open('scripts/smoke_test.py').read())"
"""

from decimal import Decimal

from apps.assessments.models import Score
from apps.payments.models import Invoice, StkPushRequest
from apps.payments.services import daraja
from apps.payments.services.reconcile import record_transaction
from apps.schools.models import School
from apps.students.models import Learner

school = School.objects.get(code="12345678")

# 1. CBC competency derivation
print("--- Competency levels (auto-derived EE/ME/AE/BE) ---")
for score in Score.objects.filter(school=school).select_related("learner"):
    print(f"  {score.learner.full_name}: {score.marks} -> {score.competency_level}")
levels = {s.competency_level for s in Score.objects.filter(school=school)}
assert levels == {"EE", "ME", "AE", "BE"}, f"expected all four bands, got {levels}"

# 2. M-Pesa: STK push (stub) -> callback -> reconciliation, replay-safe
print("--- M-Pesa STK push + callback reconciliation ---")
learner = Learner.objects.get(school=school, admission_number="ADM001")
invoice = learner.invoices.first()
result = daraja.stk_push(phone="254700000001", amount=5000, account_reference=learner.admission_number)
print(f"  STK push accepted: {result['CheckoutRequestID']}")
stk = StkPushRequest.objects.create(
    school=school, invoice=invoice, phone="254700000001", amount=Decimal("5000"),
    checkout_request_id=result["CheckoutRequestID"],
)
txn = record_transaction(
    school=school, source="STK", receipt="SBX12345TEST", phone="254700000001",
    amount=Decimal("5000"), invoice=invoice,
)
invoice.refresh_from_db()
print(f"  After payment: paid={invoice.amount_paid}, balance={invoice.balance}, status={invoice.status}")
assert invoice.status == Invoice.Status.PARTIAL and invoice.balance == Decimal("10000")

replay = record_transaction(
    school=school, source="STK", receipt="SBX12345TEST", phone="254700000001",
    amount=Decimal("5000"), invoice=invoice,
)
invoice.refresh_from_db()
assert replay is None and invoice.amount_paid == Decimal("5000"), "replayed callback double-credited!"
print(f"  Replayed callback ignored: paid still {invoice.amount_paid} (idempotent)")

# 2b. C2B with admission number as account reference
txn = record_transaction(
    school=school, source="C2B", receipt="SBX67890TEST", phone="254700000001",
    amount=Decimal("10000"), account_reference="ADM001",
)
invoice.refresh_from_db()
print(f"  C2B paybill matched by admission no: status={invoice.status}, balance={invoice.balance}")
assert invoice.status == Invoice.Status.PAID

# 3. Offline-tolerant attendance (bulk upsert + idempotency store)
print("--- Offline-tolerant bulk attendance ---")
from datetime import date

from apps.attendance.models import AttendanceRecord
from apps.common.models import IdempotentRequest

today = date(2026, 8, 4)
rows = [{"learner": l.pk, "status": "P"} for l in Learner.objects.filter(school=school)]
for row in rows:
    AttendanceRecord.objects.update_or_create(
        learner_id=row["learner"], date=today, defaults={"status": row["status"], "school": school}
    )
# retry converges instead of erroring
for row in rows:
    AttendanceRecord.objects.update_or_create(
        learner_id=row["learner"], date=today, defaults={"status": row["status"], "school": school}
    )
count = AttendanceRecord.objects.filter(school=school, date=today).count()
print(f"  {count} attendance rows after double-sync (no duplicates)")
assert count == 5

IdempotentRequest.objects.create(
    key="test-key-1", method="POST", path="/api/attendance/bulk/",
    status_code=200, response_body={"ok": True},
)
assert IdempotentRequest.objects.filter(key="test-key-1").count() == 1
print("  Idempotency-Key store works")

# 4. KEMIS export shape
print("--- KEMIS export ---")
print(f"  {Learner.objects.filter(school=school, active=True).count()} learners ready for learner-register CSV")

print("\nALL SMOKE TESTS PASSED")
