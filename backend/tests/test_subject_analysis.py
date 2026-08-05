"""Subject outcomes across the school."""

from rest_framework.test import APITestCase

from apps.assessments.models import Score
from apps.assessments.subject_analysis import subject_analysis
from apps.timetable.models import LessonRequirement
from tests.factories import (
    make_assessment,
    make_learner,
    make_learning_area,
    make_school,
    make_teacher,
    make_user,
)


class SubjectAnalysisTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.maths = make_learning_area("Mathematics", "MATH")
        self.english = make_learning_area("English", "ENG")
        self.learners = [make_learner(self.school, grade=7) for _ in range(6)]

    def _mark(self, area, marks, *, grade=7, term=1, year=2026, kind="CAT1"):
        assessment = make_assessment(
            self.school, learning_area=area, grade=grade, term=term, year=year,
            kind=kind, max_marks=100,
        )
        for learner, value in zip(self.learners, marks):
            Score.objects.create(
                school=self.school, assessment=assessment, learner=learner, marks=value
            )
        return assessment

    def test_an_unmarked_school_says_so_rather_than_showing_nothing(self):
        result = subject_analysis(self.school)
        self.assertEqual(result["subjects"], [])
        self.assertIn("once assessments have been marked", result["note"])

    def test_each_subject_gets_its_own_row(self):
        self._mark(self.maths, [70] * 6)
        self._mark(self.english, [50] * 6)
        names = {s["name"] for s in subject_analysis(self.school)["subjects"]}
        self.assertEqual(names, {"Mathematics", "English"})

    def test_the_weakest_subject_leads(self):
        """The list exists to be acted on; a subject going well needs no attention."""
        self._mark(self.maths, [85] * 6)      # all EE
        self._mark(self.english, [30] * 6)    # all BE
        result = subject_analysis(self.school)
        self.assertEqual(result["subjects"][0]["name"], "English")
        self.assertEqual(result["weakest"], "English")
        self.assertEqual(result["strongest"], "Mathematics")

    def test_a_small_cohort_is_withheld_and_sorts_last(self):
        self._mark(self.maths, [70] * 6)
        tiny = make_learning_area("Music", "MUS")
        assessment = make_assessment(self.school, learning_area=tiny, grade=7)
        for _ in range(3):
            Score.objects.create(
                school=self.school, assessment=assessment,
                learner=make_learner(self.school, grade=7), marks=10,
            )
        subjects = subject_analysis(self.school)["subjects"]
        self.assertEqual(subjects[-1]["name"], "Music")
        self.assertTrue(subjects[-1]["withheld"])
        self.assertIsNone(subjects[-1]["mean"])

    def test_it_breaks_down_by_grade(self):
        """'Mathematics is weak' is not actionable; 'Mathematics in Grade 8' is."""
        self._mark(self.maths, [80] * 6, grade=7)
        eights = [make_learner(self.school, grade=8) for _ in range(6)]
        assessment = make_assessment(self.school, learning_area=self.maths, grade=8)
        for learner in eights:
            Score.objects.create(
                school=self.school, assessment=assessment, learner=learner, marks=30
            )
        maths = next(
            s for s in subject_analysis(self.school)["subjects"] if s["name"] == "Mathematics"
        )
        by_grade = {g["grade"]: g["mean"] for g in maths["grades"]}
        self.assertEqual(by_grade[7], 80.0)
        self.assertEqual(by_grade[8], 30.0)

    def test_term_on_term_movement_is_reported(self):
        self._mark(self.maths, [40] * 6, term=1)
        self._mark(self.maths, [60] * 6, term=2)
        maths = subject_analysis(self.school)["subjects"][0]
        self.assertEqual(maths["movement"], 20.0)

    def test_it_names_who_teaches_the_subject(self):
        teacher = make_teacher(self.school)
        LessonRequirement.objects.create(
            school=self.school, teacher=teacher, learning_area=self.maths, grade=7,
        )
        self._mark(self.maths, [70] * 6)
        maths = subject_analysis(self.school)["subjects"][0]
        self.assertIn(teacher.user.get_full_name(), maths["teachers"])

    def test_marks_out_of_different_totals_compare(self):
        assessment = make_assessment(
            self.school, learning_area=self.maths, grade=7, max_marks=20
        )
        for learner in self.learners:
            Score.objects.create(
                school=self.school, assessment=assessment, learner=learner, marks=10
            )
        self.assertEqual(subject_analysis(self.school)["subjects"][0]["mean"], 50.0)

    def test_filtering_by_term_narrows_it(self):
        self._mark(self.maths, [40] * 6, term=1)
        self._mark(self.maths, [90] * 6, term=2)
        self.assertEqual(subject_analysis(self.school, term=2)["subjects"][0]["mean"], 90.0)

    def test_filtering_by_grade_narrows_it(self):
        self._mark(self.maths, [40] * 6, grade=7)
        self.assertEqual(subject_analysis(self.school, grade=8)["subjects"], [])

    def test_another_schools_marks_are_never_counted(self):
        elsewhere = make_school("Elsewhere")
        other = make_learner(elsewhere, grade=7)
        assessment = make_assessment(elsewhere, learning_area=self.maths, grade=7)
        Score.objects.create(
            school=elsewhere, assessment=assessment, learner=other, marks=100
        )
        self._mark(self.maths, [40] * 6)
        self.assertEqual(subject_analysis(self.school)["subjects"][0]["mean"], 40.0)


class SubjectAnalysisApiTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        self.head = make_teacher(self.school, rank="HEAD")
        self.teacher = make_teacher(self.school)
        maths = make_learning_area("Mathematics", "MATH")
        assessment = make_assessment(self.school, learning_area=maths, grade=7)
        for _ in range(6):
            Score.objects.create(
                school=self.school, assessment=assessment,
                learner=make_learner(self.school, grade=7), marks=65,
            )

    def test_the_admin_sees_it(self):
        self.client.force_authenticate(self.admin)
        res = self.client.get("/api/school/subject-analysis/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["subjects"][0]["mean"], 65.0)

    def test_the_head_teacher_sees_it(self):
        self.client.force_authenticate(self.head.user)
        self.assertEqual(
            self.client.get("/api/school/subject-analysis/").status_code, 200
        )

    def test_a_class_teacher_does_not(self):
        self.client.force_authenticate(self.teacher.user)
        self.assertEqual(
            self.client.get("/api/school/subject-analysis/").status_code, 403
        )

    def test_a_parent_does_not(self):
        self.client.force_authenticate(make_user(self.school, "PARENT"))
        self.assertEqual(
            self.client.get("/api/school/subject-analysis/").status_code, 403
        )

    def test_a_junk_filter_is_a_400_not_a_500(self):
        self.client.force_authenticate(self.admin)
        res = self.client.get("/api/school/subject-analysis/?term=last")
        self.assertEqual(res.status_code, 400)
