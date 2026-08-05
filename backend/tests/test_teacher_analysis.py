"""Teacher analysis, professional development records, and peer review."""

from rest_framework.test import APITestCase

from apps.assessments.models import Score
from apps.teachers.analysis import MIN_COHORT, competency_spread, teacher_analysis
from apps.teachers.models import PeerReview, ProfessionalDevelopmentRecord, SchemeOfWork
from apps.timetable.models import LessonRequirement
from tests.factories import (
    make_assessment,
    make_learner,
    make_learning_area,
    make_school,
    make_teacher,
    make_user,
)


class AnalysisTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.teacher = make_teacher(self.school)
        self.maths = make_learning_area("Mathematics", "MATH")
        LessonRequirement.objects.create(
            school=self.school, teacher=self.teacher, learning_area=self.maths,
            grade=7, stream="North",
        )
        self.learners = [
            make_learner(self.school, grade=7, stream="North") for _ in range(6)
        ]

    def _mark(self, marks, *, term=1, year=2026, kind="CAT1"):
        assessment = make_assessment(
            self.school, learning_area=self.maths, grade=7, term=term, year=year,
            kind=kind, max_marks=100, stream="North",
        )
        for learner, value in zip(self.learners, marks):
            Score.objects.create(
                school=self.school, assessment=assessment, learner=learner, marks=value
            )
        return assessment

    def test_a_teacher_with_no_timetable_has_nothing_to_attribute(self):
        other = make_teacher(self.school)
        result = teacher_analysis(other)
        self.assertEqual(result["classes"], [])
        self.assertIn("No lesson requirements", result["note"])

    def test_the_class_mean_is_a_percentage_not_raw_marks(self):
        self._mark([50, 50, 50, 50, 50, 50])
        result = teacher_analysis(self.teacher)
        self.assertEqual(result["classes"][0]["mean"], 50.0)

    def test_marks_out_of_a_different_total_still_compare(self):
        assessment = make_assessment(
            self.school, learning_area=self.maths, grade=7, stream="North",
            max_marks=20, kind="CAT2",
        )
        for learner in self.learners:
            Score.objects.create(
                school=self.school, assessment=assessment, learner=learner, marks=10
            )
        result = teacher_analysis(self.teacher)
        self.assertEqual(result["classes"][0]["mean"], 50.0)  # 10/20

    def test_a_small_cohort_is_withheld_rather_than_shown(self):
        """A mean over three learners says more about the sample than the teaching."""
        small = make_teacher(self.school)
        science = make_learning_area("Integrated Science", "SCI")
        LessonRequirement.objects.create(
            school=self.school, teacher=small, learning_area=science, grade=8,
        )
        assessment = make_assessment(self.school, learning_area=science, grade=8)
        for _ in range(MIN_COHORT - 1):
            learner = make_learner(self.school, grade=8)
            Score.objects.create(
                school=self.school, assessment=assessment, learner=learner, marks=90
            )
        row = teacher_analysis(small)["classes"][0]
        self.assertTrue(row["withheld"])
        self.assertIsNone(row["mean"])
        self.assertIn("Fewer than", row["withheld_reason"])

    def test_competency_spread_reports_those_at_or_above_expectation(self):
        self._mark([90, 85, 70, 65, 30, 20])  # EE EE ME ME BE BE
        row = teacher_analysis(self.teacher)["classes"][0]
        self.assertEqual(row["competency"]["counts"]["EE"], 2)
        self.assertEqual(row["competency"]["counts"]["ME"], 2)
        self.assertEqual(row["competency"]["counts"]["BE"], 2)
        self.assertAlmostEqual(row["competency"]["at_or_above_expectation"], 66.7, places=1)

    def test_term_on_term_movement_is_reported(self):
        self._mark([40] * 6, term=1, kind="CAT1")
        self._mark([60] * 6, term=2, kind="CAT1")
        row = teacher_analysis(self.teacher)["classes"][0]
        self.assertEqual([t["label"] for t in row["timeline"]], ["T1 2026", "T2 2026"])
        self.assertEqual(row["movement"], 20.0)

    def test_a_single_term_has_no_movement(self):
        self._mark([50] * 6)
        self.assertIsNone(teacher_analysis(self.teacher)["classes"][0]["movement"])

    def test_another_streams_marks_are_not_counted(self):
        outsider = make_learner(self.school, grade=7, stream="South")
        assessment = self._mark([50] * 6)
        Score.objects.create(
            school=self.school, assessment=assessment, learner=outsider, marks=100
        )
        row = teacher_analysis(self.teacher)["classes"][0]
        self.assertEqual(row["learners"], 6)
        self.assertEqual(row["mean"], 50.0)

    def test_the_result_says_it_is_not_a_score_for_the_teacher(self):
        self._mark([50] * 6)
        self.assertIn("not the teacher", teacher_analysis(self.teacher)["note"])

    def test_competency_spread_of_nothing_is_not_a_crash(self):
        spread = competency_spread([])
        self.assertEqual(spread["total"], 0)
        self.assertIsNone(spread["at_or_above_expectation"])


class AnalysisApiTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        self.head = make_teacher(self.school, rank="HEAD")
        self.teacher = make_teacher(self.school, supervisor=self.head.user)
        self.stranger = make_teacher(self.school)
        maths = make_learning_area("Mathematics", "MATH")
        LessonRequirement.objects.create(
            school=self.school, teacher=self.teacher, learning_area=maths, grade=7,
        )
        assessment = make_assessment(self.school, learning_area=maths, grade=7)
        for _ in range(6):
            learner = make_learner(self.school, grade=7)
            Score.objects.create(
                school=self.school, assessment=assessment, learner=learner, marks=70
            )

    def test_a_teacher_sees_their_own_analysis(self):
        self.client.force_authenticate(self.teacher.user)
        res = self.client.get(f"/api/teachers/{self.teacher.id}/analysis/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["classes"][0]["mean"], 70.0)

    def test_a_colleague_cannot_read_someone_elses(self):
        self.client.force_authenticate(self.stranger.user)
        res = self.client.get(f"/api/teachers/{self.teacher.id}/analysis/")
        self.assertEqual(res.status_code, 403)

    def test_a_supervisor_can_read_their_own_line(self):
        self.client.force_authenticate(self.head.user)
        res = self.client.get(f"/api/teachers/{self.teacher.id}/analysis/")
        self.assertEqual(res.status_code, 200)

    def test_another_schools_teacher_is_not_found(self):
        outsider = make_teacher(make_school("Elsewhere"))
        self.client.force_authenticate(self.admin)
        res = self.client.get(f"/api/teachers/{outsider.id}/analysis/")
        self.assertEqual(res.status_code, 404)

    def test_the_school_overview_is_for_the_head(self):
        self.client.force_authenticate(self.admin)
        res = self.client.get("/api/school/analysis/")
        self.assertEqual(res.status_code, 200)
        names = [t["name"] for t in res.data["teachers"]]
        self.assertIn(self.teacher.user.get_full_name(), names)
        self.assertIn("not a ranking", res.data["note"])

    def test_a_class_teacher_cannot_see_the_whole_school(self):
        self.client.force_authenticate(self.teacher.user)
        self.assertEqual(self.client.get("/api/school/analysis/").status_code, 403)

    def test_a_head_teacher_can(self):
        self.client.force_authenticate(self.head.user)
        self.assertEqual(self.client.get("/api/school/analysis/").status_code, 200)

    def test_a_parent_cannot(self):
        self.client.force_authenticate(make_user(self.school, "PARENT"))
        self.assertEqual(self.client.get("/api/school/analysis/").status_code, 403)


class PdRecordTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        self.teacher = make_teacher(self.school)
        self.other = make_teacher(self.school)

    def _payload(self, **extra):
        return {
            "title": "CBC assessment workshop",
            "provider": "TSC",
            "completed_on": "2026-04-10",
            "tpd_points": 5,
            **extra,
        }

    def test_a_teacher_logs_their_own_training(self):
        self.client.force_authenticate(self.teacher.user)
        res = self.client.post("/api/pd-records/", self._payload(), format="json")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(
            ProfessionalDevelopmentRecord.objects.get().teacher_id, self.teacher.id
        )

    def test_a_teacher_cannot_log_against_a_colleague(self):
        self.client.force_authenticate(self.teacher.user)
        res = self.client.post(
            "/api/pd-records/", self._payload(teacher=self.other.id), format="json"
        )
        self.assertEqual(res.status_code, 403)

    def test_the_admin_may_log_for_anyone(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            "/api/pd-records/", self._payload(teacher=self.other.id), format="json"
        )
        self.assertEqual(res.status_code, 201)

    def test_a_teacher_sees_only_their_own(self):
        ProfessionalDevelopmentRecord.objects.create(
            school=self.school, teacher=self.other, title="Theirs",
            completed_on="2026-01-01",
        )
        self.client.force_authenticate(self.teacher.user)
        self.assertEqual(self.client.get("/api/pd-records/").data["count"], 0)

    def test_tpd_points_total_per_teacher(self):
        for points in (5, 10):
            ProfessionalDevelopmentRecord.objects.create(
                school=self.school, teacher=self.teacher, title="Course",
                completed_on="2026-01-01", tpd_points=points,
            )
        self.client.force_authenticate(self.admin)
        res = self.client.get("/api/pd-records/summary/")
        row = next(r for r in res.data if r["teacher"] == self.teacher.id)
        self.assertEqual(row["tpd_points"], 15)

    def test_records_are_scoped_to_the_school(self):
        elsewhere = make_school("Elsewhere")
        ProfessionalDevelopmentRecord.objects.create(
            school=elsewhere, teacher=make_teacher(elsewhere), title="Theirs",
            completed_on="2026-01-01",
        )
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get("/api/pd-records/").data["count"], 0)


class PeerReviewTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.maths = make_learning_area("Mathematics", "MATH")
        self.author = make_teacher(self.school)
        self.peer = make_teacher(self.school)
        self.outsider = make_teacher(self.school)
        for teacher in (self.author, self.peer):
            LessonRequirement.objects.create(
                school=self.school, teacher=teacher, learning_area=self.maths,
                grade=7, stream="North" if teacher == self.author else "South",
            )
        self.scheme = SchemeOfWork.objects.create(
            school=self.school, teacher=self.author, learning_area=self.maths,
            grade=7, term=1, year=2026,
        )

    def test_a_colleague_can_comment(self):
        self.client.force_authenticate(self.peer.user)
        res = self.client.post(
            "/api/peer-reviews/",
            {"scheme": self.scheme.id, "verdict": "SUGGEST",
             "comment": "Week 4 needs a practical."},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(PeerReview.objects.get().reviewer_id, self.peer.user_id)

    def test_you_cannot_peer_review_your_own_scheme(self):
        self.client.force_authenticate(self.author.user)
        res = self.client.post(
            "/api/peer-reviews/",
            {"scheme": self.scheme.id, "comment": "Excellent work by me."},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_one_review_per_colleague(self):
        self.client.force_authenticate(self.peer.user)
        body = {"scheme": self.scheme.id, "comment": "First thought."}
        self.assertEqual(self.client.post("/api/peer-reviews/", body, format="json").status_code, 201)
        self.assertEqual(self.client.post("/api/peer-reviews/", body, format="json").status_code, 400)

    def test_a_review_can_only_be_edited_by_its_author(self):
        review = PeerReview.objects.create(
            school=self.school, scheme=self.scheme, reviewer=self.peer.user,
            comment="Mine",
        )
        self.client.force_authenticate(self.outsider.user)
        res = self.client.patch(
            f"/api/peer-reviews/{review.id}/", {"comment": "Hijacked"}, format="json"
        )
        self.assertEqual(res.status_code, 403)

    def test_peer_review_does_not_change_the_schemes_status(self):
        """It is advice between colleagues, not a second approval gate."""
        self.client.force_authenticate(self.peer.user)
        self.client.post(
            "/api/peer-reviews/",
            {"scheme": self.scheme.id, "verdict": "ENDORSE", "comment": "Good"},
            format="json",
        )
        self.scheme.refresh_from_db()
        self.assertEqual(self.scheme.status, "DRAFT")

    def test_the_queue_offers_colleagues_schemes_in_my_subject(self):
        self.client.force_authenticate(self.peer.user)
        res = self.client.get("/api/peer-review/queue/")
        self.assertEqual(res.status_code, 200)
        ids = [s["id"] for s in res.data["schemes"]]
        self.assertIn(self.scheme.id, ids)

    def test_the_queue_excludes_my_own_schemes(self):
        self.client.force_authenticate(self.author.user)
        res = self.client.get("/api/peer-review/queue/")
        self.assertNotIn(self.scheme.id, [s["id"] for s in res.data["schemes"]])

    def test_the_queue_drops_what_i_have_already_reviewed(self):
        PeerReview.objects.create(
            school=self.school, scheme=self.scheme, reviewer=self.peer.user,
            comment="Done",
        )
        self.client.force_authenticate(self.peer.user)
        res = self.client.get("/api/peer-review/queue/")
        self.assertEqual(res.data["schemes"], [])

    def test_a_teacher_of_another_subject_sees_nothing(self):
        self.client.force_authenticate(self.outsider.user)
        res = self.client.get("/api/peer-review/queue/")
        self.assertEqual(res.data["schemes"], [])

    def test_non_teaching_staff_cannot_peer_review(self):
        from tests.factories import make_support

        cook = make_support(self.school)
        self.client.force_authenticate(cook.user)
        self.assertEqual(self.client.get("/api/peer-review/queue/").status_code, 403)
