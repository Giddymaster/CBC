"""What school leadership (head teacher, deputy) may do beyond a teacher."""

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.teachers.models import TeacherAttendance
from apps.timetable.models import LessonRequirement
from tests.factories import (
    make_learning_area,
    make_school,
    make_teacher,
    make_user,
)


class AssignmentPermissionTests(APITestCase):
    """Teaching assignments are set by the admin, head teacher or deputy."""

    def setUp(self):
        self.school = make_school()
        self.maths = make_learning_area("Mathematics", "MATH")
        self.head = make_teacher(self.school, rank="HEAD")
        self.teacher = make_teacher(self.school)

    def _assign(self, as_user):
        self.client.force_authenticate(as_user)
        return self.client.post(
            "/api/timetable/requirements/",
            {
                "teacher": self.teacher.id, "learning_area": self.maths.id,
                "grade": 7, "stream": "", "lessons_per_week": 5,
            },
            format="json",
        )

    def test_the_head_teacher_assigns(self):
        res = self._assign(self.head.user)
        self.assertEqual(res.status_code, 201, res.data)
        self.assertTrue(
            LessonRequirement.objects.filter(teacher=self.teacher).exists()
        )

    def test_a_deputy_assigns(self):
        deputy = make_teacher(self.school, rank="DEPUTY")
        self.assertEqual(self._assign(deputy.user).status_code, 201)

    def test_an_ordinary_teacher_does_not(self):
        res = self._assign(self.teacher.user)
        self.assertEqual(res.status_code, 403)
        self.assertFalse(LessonRequirement.objects.exists())

    def test_the_head_teacher_removes_an_assignment(self):
        req = LessonRequirement.objects.create(
            school=self.school, teacher=self.teacher, learning_area=self.maths,
            grade=7, lessons_per_week=5,
        )
        self.client.force_authenticate(self.head.user)
        res = self.client.delete(f"/api/timetable/requirements/{req.id}/")
        self.assertEqual(res.status_code, 204)


class RollCallHistoryTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        self.teacher = make_teacher(self.school)

    def test_history_shows_the_marks_over_school_days(self):
        today = timezone.localdate()
        # Mark the most recent weekday (today if it is one, else last Friday).
        day = today
        while day.weekday() >= 5:
            day -= timezone.timedelta(days=1)
        TeacherAttendance.objects.create(
            school=self.school, teacher=self.teacher, date=day, status="A"
        )
        self.client.force_authenticate(self.admin)
        res = self.client.get("/api/staff/roll-call/history/?days=10")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data["days"]), 10)
        self.assertEqual(res.data["days"][-1], day.isoformat())
        (row,) = res.data["staff"]
        self.assertEqual(row["marks"][day.isoformat()], "A")
        self.assertEqual(row["totals"]["absent"], 1)

    def test_an_ordinary_teacher_cannot_read_the_history(self):
        self.client.force_authenticate(self.teacher.user)
        res = self.client.get("/api/staff/roll-call/history/")
        self.assertEqual(res.status_code, 403)
