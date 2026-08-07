"""The teacher-portal summary endpoint — specifically the assessments payload
the score-entry screen builds itself from."""

from rest_framework.test import APITestCase

from apps.timetable.models import LessonRequirement
from tests.factories import (
    make_assessment,
    make_learning_area,
    make_school,
    make_teacher,
)


class TeacherSummaryAssessmentsTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.teacher = make_teacher(self.school)
        self.maths = make_learning_area("Mathematics", "MATH")
        LessonRequirement.objects.create(
            school=self.school, teacher=self.teacher, learning_area=self.maths,
            grade=5, lessons_per_week=5,
        )

    def test_an_assessment_carries_marks_and_banding_for_live_preview(self):
        """The client shows the competency level as marks are typed, so it
        needs max_marks and the (possibly empty) rubric override."""
        make_assessment(
            self.school, learning_area=self.maths, grade=5, max_marks=60,
            rubric=[[80, "EE"], [60, "ME"], [40, "AE"], [0, "BE"]],
        )
        self.client.force_authenticate(self.teacher.user)
        res = self.client.get("/api/teacher/summary/")
        self.assertEqual(res.status_code, 200)
        (assessment,) = res.data["assessments"]
        self.assertEqual(assessment["max_marks"], 60)
        self.assertEqual(assessment["rubric"][0], [80, "EE"])

    def test_the_default_banding_ships_as_an_empty_rubric(self):
        make_assessment(self.school, learning_area=self.maths, grade=5)
        self.client.force_authenticate(self.teacher.user)
        res = self.client.get("/api/teacher/summary/")
        (assessment,) = res.data["assessments"]
        self.assertEqual(assessment["rubric"], [])

    def test_other_teachers_assessments_stay_out_of_the_list(self):
        other_area = make_learning_area("Kiswahili", "KIS")
        make_assessment(self.school, learning_area=other_area, grade=6)
        self.client.force_authenticate(self.teacher.user)
        res = self.client.get("/api/teacher/summary/")
        self.assertEqual(res.data["assessments"], [])
