"""Phase-bound teaching, the G4-G9 generator scope, and the standard day."""

from rest_framework.test import APITestCase

from apps.timetable.generator import generate_timetable, seed_standard_day
from apps.timetable.models import Lesson, LessonRequirement, Period
from tests.factories import make_learning_area, make_school, make_teacher, make_user


class PhaseRulesTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        self.maths = make_learning_area("Mathematics", "MATH")

    def _assign(self, teacher, grade):
        self.client.force_authenticate(self.admin)
        return self.client.post(
            "/api/timetable/requirements/",
            {"teacher": teacher.id, "learning_area": self.maths.id,
             "grade": grade, "stream": "", "lessons_per_week": 5},
            format="json",
        )

    def test_a_junior_school_teacher_cannot_take_a_primary_class(self):
        jss = make_teacher(self.school, phase="JUNIOR")
        res = self._assign(jss, 5)
        self.assertEqual(res.status_code, 400)
        self.assertIn("Junior School", res.data["teacher"][0])

    def test_a_primary_teacher_cannot_take_a_junior_class(self):
        primary = make_teacher(self.school, phase="PRIMARY")
        self.assertEqual(self._assign(primary, 8).status_code, 400)

    def test_each_phase_works_inside_its_band(self):
        self.assertEqual(self._assign(make_teacher(self.school, phase="PRIMARY"), 4).status_code, 201)
        self.assertEqual(self._assign(make_teacher(self.school, phase="JUNIOR"), 9).status_code, 201)
        self.assertEqual(self._assign(make_teacher(self.school, phase="PRE_PRIMARY"), 0).status_code, 201)

    def test_an_unphased_teacher_may_teach_anywhere(self):
        floater = make_teacher(self.school)
        self.assertEqual(self._assign(floater, 8).status_code, 201)


class GeneratorScopeTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.maths = make_learning_area("Mathematics", "MATH")
        seed_standard_day(self.school)

    def test_the_standard_day_has_nine_lessons_and_is_idempotent(self):
        periods = Period.objects.filter(school=self.school).order_by("number")
        self.assertEqual(periods.count(), 9)
        self.assertEqual(str(periods.first().start_time), "07:30:00")
        self.assertEqual(str(periods.last().end_time), "16:00:00")
        self.assertEqual(seed_standard_day(self.school), 0)  # nothing new
        self.assertEqual(Period.objects.filter(school=self.school).count(), 9)

    def test_only_grades_4_to_9_are_scheduled(self):
        upper = make_teacher(self.school, phase="PRIMARY")
        lower = make_teacher(self.school, phase="PRE_PRIMARY")
        LessonRequirement.objects.create(
            school=self.school, teacher=upper, learning_area=self.maths,
            grade=5, lessons_per_week=5,
        )
        LessonRequirement.objects.create(
            school=self.school, teacher=lower, learning_area=self.maths,
            grade=-1, lessons_per_week=5,
        )
        report = generate_timetable(self.school)
        self.assertEqual(report["placed"], 5)
        self.assertEqual(report["lower_grades_skipped"], 1)
        self.assertFalse(Lesson.objects.filter(grade=-1).exists())
        self.assertEqual(Lesson.objects.filter(grade=5).count(), 5)
