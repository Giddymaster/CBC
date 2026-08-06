"""The parts a school would notice first if they broke: marks and competency
levels, the attendance register, fee payments, the timetable, and the grade
structure."""

from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.assessments.models import Score, derive_competency_level
from apps.attendance.models import AttendanceRecord
from apps.payments.models import FeeStructure, Invoice, MpesaTransaction
from apps.payments.services.reconcile import record_transaction
from apps.timetable.models import Lesson, Period, Room
from tests.factories import (
    make_assessment,
    make_learner,
    make_learning_area,
    make_school,
    make_teacher,
    make_user,
)


class CompetencyTests(APITestCase):
    def test_rubric_bands(self):
        self.assertEqual(derive_competency_level(95), "EE")
        self.assertEqual(derive_competency_level(80), "EE")
        self.assertEqual(derive_competency_level(79.9), "ME")
        self.assertEqual(derive_competency_level(60), "ME")
        self.assertEqual(derive_competency_level(40), "AE")
        self.assertEqual(derive_competency_level(39.9), "BE")
        self.assertEqual(derive_competency_level(0), "BE")

    def test_level_is_derived_from_percentage_not_raw_marks(self):
        school = make_school()
        assessment = make_assessment(school, max_marks=20)
        learner = make_learner(school)
        score = Score.objects.create(school=school, assessment=assessment, learner=learner, marks=17)
        self.assertEqual(score.competency_level, "EE")  # 85%

    def test_school_can_override_the_rubric(self):
        school = make_school()
        assessment = make_assessment(school, rubric=[[90, "EE"], [70, "ME"], [50, "AE"]])
        learner = make_learner(school)
        score = Score.objects.create(school=school, assessment=assessment, learner=learner, marks=85)
        self.assertEqual(score.competency_level, "ME")


class BulkScoreTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.teacher = make_teacher(self.school)
        self.assessment = make_assessment(self.school, grade=5, max_marks=100)
        self.learners = [make_learner(self.school, grade=5) for _ in range(3)]
        self.client.force_authenticate(self.teacher.user)

    def _payload(self, marks):
        return {
            "assessment": self.assessment.id,
            "records": [
                {"learner": l.id, "marks": m} for l, m in zip(self.learners, marks)
            ],
        }

    def test_bulk_entry_derives_levels(self):
        res = self.client.post("/api/scores/bulk/", self._payload([90, 65, 30]), format="json")
        self.assertEqual(res.status_code, 200)
        levels = {row["learner"]: row["competency_level"] for row in res.data["saved"]}
        self.assertEqual(levels[self.learners[0].id], "EE")
        self.assertEqual(levels[self.learners[1].id], "ME")
        self.assertEqual(levels[self.learners[2].id], "BE")

    def test_bulk_entry_upserts_rather_than_duplicating(self):
        self.client.post("/api/scores/bulk/", self._payload([90, 65, 30]), format="json")
        self.client.post("/api/scores/bulk/", self._payload([40, 65, 30]), format="json")
        self.assertEqual(Score.objects.count(), 3)
        self.assertEqual(
            Score.objects.get(learner=self.learners[0]).competency_level, "AE"
        )

    def test_marks_above_max_are_rejected_not_stored(self):
        res = self.client.post("/api/scores/bulk/", self._payload([150, 65, 30]), format="json")
        saved = [row["learner"] for row in res.data["saved"]]
        self.assertNotIn(self.learners[0].id, saved)
        self.assertTrue(res.data["skipped"])

    def test_marks_for_another_schools_learner_are_skipped(self):
        intruder = make_learner(make_school("Elsewhere"), grade=5)
        res = self.client.post(
            "/api/scores/bulk/",
            {"assessment": self.assessment.id, "records": [{"learner": intruder.id, "marks": 50}]},
            format="json",
        )
        self.assertFalse(Score.objects.filter(learner=intruder).exists())
        self.assertEqual(res.data["saved"], [])


class AttendanceAndIdempotencyTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.teacher = make_teacher(self.school)
        self.learners = [make_learner(self.school, grade=5) for _ in range(3)]
        self.client.force_authenticate(self.teacher.user)
        self.today = timezone.localdate()

    def _payload(self, statuses):
        return {
            "date": self.today.isoformat(),
            "records": [
                {"learner": l.id, "status": s} for l, s in zip(self.learners, statuses)
            ],
        }

    def test_bulk_register_saves_the_class(self):
        res = self.client.post("/api/attendance/bulk/", self._payload("PAP"), format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(AttendanceRecord.objects.count(), 3)

    def test_resubmitting_the_register_corrects_rather_than_duplicates(self):
        self.client.post("/api/attendance/bulk/", self._payload("PAP"), format="json")
        self.client.post("/api/attendance/bulk/", self._payload("PPP"), format="json")
        self.assertEqual(AttendanceRecord.objects.count(), 3)
        self.assertEqual(
            AttendanceRecord.objects.filter(status="A").count(), 0
        )

    def test_idempotency_key_replays_the_stored_response(self):
        key = str(uuid4())
        first = self.client.post(
            "/api/attendance/bulk/",
            self._payload("PAP"),
            format="json",
            HTTP_IDEMPOTENCY_KEY=key,
        )
        second = self.client.post(
            "/api/attendance/bulk/",
            self._payload("AAA"),  # a corrupted retry must not take effect
            format="json",
            HTTP_IDEMPOTENCY_KEY=key,
        )
        self.assertEqual(second.status_code, first.status_code)
        self.assertEqual(second.get("X-Idempotent-Replay"), "true")
        self.assertEqual(AttendanceRecord.objects.filter(status="A").count(), 1)

    def test_a_different_key_is_processed_normally(self):
        self.client.post(
            "/api/attendance/bulk/", self._payload("PAP"), format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid4()),
        )
        res = self.client.post(
            "/api/attendance/bulk/", self._payload("AAA"), format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid4()),
        )
        self.assertIsNone(res.get("X-Idempotent-Replay"))
        self.assertEqual(AttendanceRecord.objects.filter(status="A").count(), 3)


class PaymentTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.learner = make_learner(self.school, grade=5, admission_number="ADM777")
        self.fee = FeeStructure.objects.create(
            school=self.school, grade=5, term=1, year=2026, amount=Decimal("10000")
        )
        self.invoice = Invoice.objects.create(
            school=self.school, learner=self.learner, fee_structure=self.fee,
            amount_due=Decimal("10000"),
        )

    def test_payment_credits_the_invoice(self):
        record_transaction(
            school=self.school, source="C2B", receipt="RCPT001", phone="254700000001",
            amount=Decimal("4000"), account_reference="ADM777",
        )
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amount_paid, Decimal("4000"))
        self.assertEqual(self.invoice.status, "PARTIAL")

    def test_replayed_callback_cannot_double_credit(self):
        for _ in range(3):
            record_transaction(
                school=self.school, source="C2B", receipt="RCPT002", phone="254700000001",
                amount=Decimal("10000"), account_reference="ADM777",
            )
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amount_paid, Decimal("10000"))
        self.assertEqual(self.invoice.status, "PAID")
        self.assertEqual(MpesaTransaction.objects.filter(mpesa_receipt="RCPT002").count(), 1)

    def test_unmatched_payment_is_kept_for_manual_review(self):
        record_transaction(
            school=self.school, source="C2B", receipt="RCPT003", phone="254700000001",
            amount=Decimal("500"), account_reference="NOSUCHADM",
        )
        txn = MpesaTransaction.objects.get(mpesa_receipt="RCPT003")
        self.assertIsNone(txn.invoice_id)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amount_paid, Decimal("0"))


class TimetableTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.period = Period.objects.create(
            school=self.school, number=1, start_time="08:00", end_time="08:40"
        )
        self.room = Room.objects.create(school=self.school, name="Room 1")
        self.area = make_learning_area()
        self.teacher = make_teacher(self.school)

    def _lesson(self, **kwargs):
        data = dict(
            school=self.school, day=1, period=self.period, teacher=self.teacher,
            learning_area=self.area, grade=5, stream="North", room=self.room,
        )
        data.update(kwargs)
        lesson = Lesson(**data)
        lesson.full_clean()
        lesson.save()
        return lesson

    def test_teacher_double_booking_is_rejected(self):
        self._lesson()
        with self.assertRaises(ValidationError):
            self._lesson(grade=6, room=None)

    def test_class_double_booking_is_rejected(self):
        self._lesson()
        other = make_teacher(self.school)
        with self.assertRaises(ValidationError):
            self._lesson(teacher=other, room=None)

    def test_room_double_booking_is_rejected(self):
        self._lesson()
        other = make_teacher(self.school)
        with self.assertRaises(ValidationError):
            self._lesson(teacher=other, grade=6)

    def test_a_free_slot_is_accepted(self):
        self._lesson()
        other = make_teacher(self.school)
        second = Room.objects.create(school=self.school, name="Room 2")
        self._lesson(teacher=other, grade=6, room=second)
        self.assertEqual(Lesson.objects.count(), 2)


class SchoolStructureTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        for grade in (-2, -1, 0, 1, 7, 10):
            make_learner(self.school, grade=grade)
        self.client.force_authenticate(self.admin)

    def test_categories_cover_play_group_through_senior(self):
        res = self.client.get("/api/school/structure/")
        self.assertEqual(res.status_code, 200)
        names = [c["name"] for c in res.data["categories"]]
        self.assertEqual(names, ["Pre-Primary", "Primary", "Junior School", "Senior School"])
        pre = next(c for c in res.data["categories"] if c["name"] == "Pre-Primary")
        self.assertEqual([g["label"] for g in pre["grades"]], ["PG", "PP1", "PP2"])

    def test_play_group_enrolment_is_counted(self):
        res = self.client.get("/api/school/structure/")
        pre = next(c for c in res.data["categories"] if c["name"] == "Pre-Primary")
        pg = next(g for g in pre["grades"] if g["label"] == "PG")
        self.assertEqual(pg["total"], 1)

    def test_play_group_detail_opens(self):
        res = self.client.get("/api/school/grades/-2/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data["students"]), 1)


class InteropTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        make_learner(self.school, grade=5, gender="M")
        make_learner(self.school, grade=5, gender="F")
        self.other = make_learner(make_school("Elsewhere"), grade=5)
        self.client.force_authenticate(self.admin)

    def test_kemis_csv_contains_only_our_learners(self):
        res = self.client.get("/api/interop/kemis/learners.csv")
        self.assertEqual(res.status_code, 200)
        body = b"".join(res.streaming_content).decode() if res.streaming else res.content.decode()
        self.assertNotIn(self.other.admission_number, body)

    def test_enrollment_counts_by_grade_and_gender(self):
        res = self.client.get("/api/interop/kemis/enrollment/")
        self.assertEqual(res.status_code, 200)
        row = next(r for r in res.data["rows"] if r["grade"] == 5)
        self.assertEqual(row["male"], 1)
        self.assertEqual(row["female"], 1)
        self.assertEqual(row["total"], 2)
