"""Attendance: who marks, half days, and the month calendar."""

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.attendance.models import AttendanceRecord
from tests.factories import make_learner, make_school, make_teacher, make_user


class MarkingRulesTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        self.teacher = make_teacher(self.school)
        self.learner = make_learner(self.school, grade=4)
        self.payload = {
            "date": timezone.localdate().isoformat(),
            "records": [{"learner": self.learner.id, "status": "H"}],
        }

    def test_the_admin_cannot_mark_the_register(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post("/api/attendance/bulk/", self.payload, format="json")
        self.assertEqual(res.status_code, 403)
        self.assertIn("class teacher", res.data["detail"])
        self.assertFalse(AttendanceRecord.objects.exists())

    def test_a_teacher_marks_and_half_day_is_a_real_status(self):
        self.client.force_authenticate(self.teacher.user)
        res = self.client.post("/api/attendance/bulk/", self.payload, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        record = AttendanceRecord.objects.get()
        self.assertEqual(record.status, "H")

    def test_junk_statuses_are_skipped_not_stored(self):
        self.client.force_authenticate(self.teacher.user)
        res = self.client.post(
            "/api/attendance/bulk/",
            {
                "date": timezone.localdate().isoformat(),
                "records": [{"learner": self.learner.id, "status": "Z"}],
            },
            format="json",
        )
        self.assertEqual(res.data["skipped"], [self.learner.id])
        self.assertFalse(AttendanceRecord.objects.exists())


class MonthViewTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        self.learner = make_learner(self.school, grade=4)
        make_learner(self.school, grade=5)  # another grade, filtered out
        today = timezone.localdate()
        AttendanceRecord.objects.create(
            school=self.school, learner=self.learner, date=today, status="A"
        )
        self.today = today

    def test_the_month_grid_returns_school_days_and_marks(self):
        self.client.force_authenticate(self.admin)
        res = self.client.get(
            f"/api/attendance/month/?year={self.today.year}"
            f"&month={self.today.month}&grade=4"
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(all(d["dow"] < 5 for d in res.data["days"]))
        (row,) = res.data["learners"]
        self.assertEqual(row["id"], self.learner.id)
        if self.today.weekday() < 5:
            self.assertEqual(row["marks"][self.today.isoformat()], "A")

    def test_a_parent_cannot_read_the_month_grid(self):
        parent = make_user(self.school, "PARENT")
        self.client.force_authenticate(parent)
        res = self.client.get("/api/attendance/month/")
        self.assertEqual(res.status_code, 403)
