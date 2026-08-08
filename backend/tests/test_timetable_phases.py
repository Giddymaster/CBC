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


class AutoAssignTests(APITestCase):
    """Auto-assign shares the WHOLE week out: periods x 5 days across the
    class's teachable subjects, cores absorbing the extras."""

    def setUp(self):
        from apps.students.models import ClassGroup

        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        ClassGroup.objects.create(school=self.school, grade=7, stream="North")

    def _areas(self, names):
        out = []
        for i, name in enumerate(names):
            area = make_learning_area(name, f"A{i}", grades=[7])
            teacher = make_teacher(self.school, phase="JUNIOR")
            teacher.learning_areas.set([area])
            out.append(area)
        return out

    def _run(self):
        self.client.force_authenticate(self.admin)
        return self.client.post("/api/timetable/assignments/auto/", {}, format="json")

    def test_nine_subjects_get_five_lessons_each(self):
        self._areas([f"Subject {i}" for i in range(9)])
        res = self._run()
        self.assertEqual(res.data["created"], 9)
        self.assertEqual(res.data["unfilled"], [])
        for req in LessonRequirement.objects.all():
            self.assertEqual(req.lessons_per_week, 5)

    def test_eight_subjects_still_fill_all_45_slots_cores_first(self):
        self._areas(["English", "Kiswahili", "Mathematics",
                     "Science", "Social", "Agriculture", "Creative", "Religious"])
        res = self._run()
        self.assertEqual(res.data["unfilled"], [])
        reqs = {r.learning_area.name: r.lessons_per_week
                for r in LessonRequirement.objects.select_related("learning_area")}
        self.assertEqual(sum(reqs.values()), 45)
        self.assertEqual(reqs["English"], 6)
        self.assertEqual(reqs["Kiswahili"], 6)
        self.assertEqual(reqs["Mathematics"], 6)
        self.assertEqual(sorted(reqs.values()), [5, 5, 5, 6, 6, 6, 6, 6])

    def test_rerunning_rebalances_a_flat_five_week(self):
        areas = self._areas(["English", "Kiswahili", "Mathematics", "Science"])
        # An earlier hand-made assignment at the old flat 5.
        old = LessonRequirement.objects.create(
            school=self.school,
            teacher=make_teacher(self.school, phase="JUNIOR"),
            learning_area=areas[0], grade=7, stream="North", lessons_per_week=5,
        )
        old.teacher.learning_areas.set([areas[0]])
        res = self._run()
        old.refresh_from_db()
        # 45 over 4 subjects: base 11, remainder 1 → English carries 12.
        self.assertEqual(old.lessons_per_week, 12)
        self.assertGreaterEqual(res.data["rebalanced"], 1)
        total = sum(r.lessons_per_week for r in LessonRequirement.objects.all())
        self.assertEqual(total, 45)

    def test_rerunning_a_settled_school_changes_nothing(self):
        self._areas([f"Subject {i}" for i in range(9)])
        self._run()
        res = self._run()
        self.assertEqual(res.data["created"], 0)
        self.assertEqual(res.data["rebalanced"], 0)

    def test_an_unstaffed_area_is_reported_and_the_rest_absorb_its_slots(self):
        self._areas([f"Subject {i}" for i in range(8)])
        make_learning_area("Kiswahili", "KIS", grades=[7])  # nobody teaches it
        res = self._run()
        self.assertEqual(
            [u["area"] for u in res.data["unfilled"]], ["Kiswahili"]
        )
        total = sum(r.lessons_per_week for r in LessonRequirement.objects.all())
        self.assertEqual(total, 45)  # the eight staffed subjects fill the week

    def test_a_primary_phase_teacher_is_not_pulled_into_jss(self):
        maths = make_learning_area("Mathematics", "MATH", grades=[7])
        primary = make_teacher(self.school, phase="PRIMARY")
        primary.learning_areas.set([maths])
        res = self._run()
        self.assertFalse(LessonRequirement.objects.filter(teacher=primary).exists())
        self.assertEqual([u["area"] for u in res.data["unfilled"]], ["Mathematics"])


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

    def test_a_subject_moves_around_the_day_not_one_fixed_slot(self):
        """Five lessons a week must not sit at the same period all five days —
        a Monday identical to Friday is not a timetable."""
        teacher = make_teacher(self.school, phase="JUNIOR")
        LessonRequirement.objects.create(
            school=self.school, teacher=teacher, learning_area=self.maths,
            grade=7, lessons_per_week=5,
        )
        generate_timetable(self.school)
        period_numbers = {
            lesson.period.number
            for lesson in Lesson.objects.filter(school=self.school)
        }
        self.assertGreater(len(period_numbers), 1)

    def test_a_full_class_week_fills_completely(self):
        """Nine subjects x five lessons = all 45 slots of one class, across
        nine different teachers — nothing may be left unplaced."""
        for i in range(9):
            area = make_learning_area(f"Area {i}", f"AR{i}", grades=[7])
            teacher = make_teacher(self.school, phase="JUNIOR")
            LessonRequirement.objects.create(
                school=self.school, teacher=teacher, learning_area=area,
                grade=7, stream="North", lessons_per_week=5,
            )
        report = generate_timetable(self.school)
        self.assertEqual(report["placed"], 45)
        self.assertEqual(report["unplaced"], [])
        # Every day carries all nine periods for this class.
        for day in range(1, 6):
            self.assertEqual(
                Lesson.objects.filter(school=self.school, day=day).count(), 9
            )

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
