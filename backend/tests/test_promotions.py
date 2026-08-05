"""End-of-year rollover: preview, adjust, apply, reverse."""

from rest_framework.test import APITestCase

from apps.promotions.models import AcademicYear, PromotionOutcome, PromotionRun
from apps.promotions.services import apply_run, build_run, propose_pathway, revert_run
from apps.schools import moe
from apps.students.models import Learner, Pathway
from tests.factories import (
    make_assessment,
    make_learner,
    make_learning_area,
    make_school,
    make_teacher,
    make_user,
)


def pathways():
    for p in moe.PATHWAYS:
        Pathway.objects.get_or_create(code=p["code"])


class PreviewTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        pathways()

    def test_every_active_learner_gets_an_outcome(self):
        for grade in (-2, 1, 6, 9, 12):
            make_learner(self.school, grade=grade)
        run = build_run(school=self.school, from_year=2026, to_year=2027)
        self.assertEqual(run.outcomes.count(), 5)
        self.assertEqual(run.status, "DRAFT")

    def test_preview_changes_nothing(self):
        learner = make_learner(self.school, grade=6)
        build_run(school=self.school, from_year=2026, to_year=2027)
        learner.refresh_from_db()
        self.assertEqual(learner.grade, 6)

    def test_each_grade_moves_up_one(self):
        pg = make_learner(self.school, grade=-2)
        six = make_learner(self.school, grade=6)
        run = build_run(school=self.school, from_year=2026, to_year=2027)
        by_learner = {o.learner_id: o for o in run.outcomes.all()}
        self.assertEqual(by_learner[pg.id].to_grade, -1)   # PG -> PP1
        self.assertEqual(by_learner[six.id].to_grade, 7)   # Primary -> Junior

    def test_grade_twelve_graduates_rather_than_promoting(self):
        twelve = make_learner(self.school, grade=12)
        run = build_run(school=self.school, from_year=2026, to_year=2027)
        outcome = run.outcomes.get(learner=twelve)
        self.assertEqual(outcome.action, "GRADUATE")
        self.assertIsNone(outcome.to_grade)

    def test_an_inactive_learner_is_left_out(self):
        make_learner(self.school, grade=5, active=False)
        run = build_run(school=self.school, from_year=2026, to_year=2027)
        self.assertEqual(run.outcomes.count(), 0)

    def test_a_run_can_be_limited_to_one_grade(self):
        make_learner(self.school, grade=5)
        make_learner(self.school, grade=9)
        run = build_run(school=self.school, from_year=2026, to_year=2027, grade=9)
        self.assertEqual(run.outcomes.count(), 1)

    def test_another_schools_learners_are_never_included(self):
        make_learner(self.school, grade=5)
        make_learner(make_school("Elsewhere"), grade=5)
        run = build_run(school=self.school, from_year=2026, to_year=2027)
        self.assertEqual(run.outcomes.count(), 1)


class PathwayProposalTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        pathways()
        self.maths = make_learning_area("Mathematics", "MATH")
        self.science = make_learning_area("Integrated Science", "SCI")
        self.art = make_learning_area("Creative Arts", "ART")

    def _score(self, learner, area, marks):
        from apps.assessments.models import Score

        assessment = make_assessment(
            self.school, learning_area=area, grade=9, max_marks=100
        )
        Score.objects.create(
            school=self.school, assessment=assessment, learner=learner, marks=marks
        )

    def test_strong_science_marks_propose_stem(self):
        learner = make_learner(self.school, grade=9)
        self._score(learner, self.maths, 88)
        self._score(learner, self.science, 91)
        self._score(learner, self.art, 44)
        code, rationale = propose_pathway(learner)
        self.assertEqual(code, "STEM")
        self.assertIn("STEM", rationale["averages"])

    def test_strong_arts_marks_propose_arts_and_sports(self):
        learner = make_learner(self.school, grade=9)
        self._score(learner, self.maths, 41)
        self._score(learner, self.art, 93)
        code, _ = propose_pathway(learner)
        self.assertEqual(code, "ARTS_SPORTS")

    def test_no_marks_proposes_nothing_and_says_why(self):
        learner = make_learner(self.school, grade=9)
        code, rationale = propose_pathway(learner)
        self.assertIsNone(code)
        self.assertIn("no marks", rationale["basis"])

    def test_the_proposal_carries_its_reasoning(self):
        learner = make_learner(self.school, grade=9)
        self._score(learner, self.science, 80)
        _, rationale = propose_pathway(learner)
        self.assertIn("Integrated Science", rationale["subjects"]["STEM"])
        self.assertIn("Advisory", rationale["note"])

    def test_grade_nine_outcomes_carry_a_proposal(self):
        learner = make_learner(self.school, grade=9)
        self._score(learner, self.science, 90)
        run = build_run(school=self.school, from_year=2026, to_year=2027)
        outcome = run.outcomes.get(learner=learner)
        self.assertEqual(outcome.to_grade, 10)
        self.assertEqual(outcome.pathway.code, "STEM")
        self.assertTrue(outcome.pathway_rationale)

    def test_other_grades_get_no_pathway(self):
        learner = make_learner(self.school, grade=8)
        run = build_run(school=self.school, from_year=2026, to_year=2027)
        self.assertIsNone(run.outcomes.get(learner=learner).pathway_id)


class ApplyTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        pathways()

    def test_applying_moves_the_learner(self):
        learner = make_learner(self.school, grade=6, stream="North")
        run = build_run(school=self.school, from_year=2026, to_year=2027)
        apply_run(run, user=self.admin)
        learner.refresh_from_db()
        self.assertEqual(learner.grade, 7)
        self.assertEqual(learner.stream, "North")
        self.assertEqual(run.status, "APPLIED")

    def test_repeat_holds_the_learner_where_they_are(self):
        learner = make_learner(self.school, grade=5)
        run = build_run(school=self.school, from_year=2026, to_year=2027)
        run.outcomes.update(action="REPEAT")
        apply_run(run, user=self.admin)
        learner.refresh_from_db()
        self.assertEqual(learner.grade, 5)
        self.assertTrue(learner.active)

    def test_graduating_marks_the_learner_as_completed(self):
        learner = make_learner(self.school, grade=12)
        run = build_run(school=self.school, from_year=2026, to_year=2027)
        apply_run(run, user=self.admin)
        learner.refresh_from_db()
        self.assertEqual(learner.status, "GRADUATED")
        self.assertFalse(learner.active)
        self.assertIsNotNone(learner.exit_date)

    def test_transfer_out_records_why_the_learner_left(self):
        learner = make_learner(self.school, grade=4)
        run = build_run(school=self.school, from_year=2026, to_year=2027)
        run.outcomes.update(action="TRANSFER", note="Moved to Nakuru")
        apply_run(run, user=self.admin)
        learner.refresh_from_db()
        self.assertEqual(learner.status, "TRANSFERRED")
        self.assertFalse(learner.active)
        self.assertEqual(learner.exit_note, "Moved to Nakuru")

    def test_the_pathway_is_written_at_grade_ten(self):
        learner = make_learner(self.school, grade=9)
        run = build_run(school=self.school, from_year=2026, to_year=2027)
        outcome = run.outcomes.get(learner=learner)
        outcome.pathway = Pathway.objects.get(code="SOCIAL")
        outcome.save()
        apply_run(run, user=self.admin)
        learner.refresh_from_db()
        self.assertEqual(learner.grade, 10)
        self.assertEqual(learner.pathway.code, "SOCIAL")

    def test_applying_rolls_the_academic_year_forward(self):
        make_learner(self.school, grade=5)
        AcademicYear.objects.create(school=self.school, year=2026, is_current=True)
        run = build_run(school=self.school, from_year=2026, to_year=2027)
        apply_run(run, user=self.admin)
        self.assertEqual(
            AcademicYear.objects.get(school=self.school, is_current=True).year, 2027
        )

    def test_a_run_cannot_be_applied_twice(self):
        make_learner(self.school, grade=5)
        run = build_run(school=self.school, from_year=2026, to_year=2027)
        apply_run(run, user=self.admin)
        with self.assertRaises(ValueError):
            apply_run(run, user=self.admin)


class RevertTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        pathways()

    def test_reverting_restores_the_grade_and_stream(self):
        learner = make_learner(self.school, grade=6, stream="North")
        run = build_run(school=self.school, from_year=2026, to_year=2027)
        apply_run(run, user=self.admin)
        revert_run(run, user=self.admin)
        learner.refresh_from_db()
        self.assertEqual(learner.grade, 6)
        self.assertEqual(learner.stream, "North")
        self.assertEqual(run.status, "REVERSED")

    def test_reverting_brings_a_graduate_back(self):
        learner = make_learner(self.school, grade=12)
        run = build_run(school=self.school, from_year=2026, to_year=2027)
        apply_run(run, user=self.admin)
        revert_run(run, user=self.admin)
        learner.refresh_from_db()
        self.assertEqual(learner.status, "ENROLLED")
        self.assertTrue(learner.active)
        self.assertIsNone(learner.exit_date)
        self.assertEqual(learner.grade, 12)

    def test_reverting_undoes_the_pathway(self):
        learner = make_learner(self.school, grade=9)
        run = build_run(school=self.school, from_year=2026, to_year=2027)
        run.outcomes.update(pathway=Pathway.objects.get(code="STEM"))
        apply_run(run, user=self.admin)
        revert_run(run, user=self.admin)
        learner.refresh_from_db()
        self.assertIsNone(learner.pathway_id)
        self.assertEqual(learner.grade, 9)

    def test_reverting_rolls_the_year_back(self):
        make_learner(self.school, grade=5)
        AcademicYear.objects.create(school=self.school, year=2026, is_current=True)
        run = build_run(school=self.school, from_year=2026, to_year=2027)
        apply_run(run, user=self.admin)
        revert_run(run, user=self.admin)
        self.assertEqual(
            AcademicYear.objects.get(school=self.school, is_current=True).year, 2026
        )

    def test_reverting_restores_the_year_even_if_it_was_never_recorded(self):
        """A school that promotes without having created the closing year must
        not be left with no current year at all."""
        make_learner(self.school, grade=5)
        self.assertFalse(AcademicYear.objects.filter(school=self.school).exists())
        run = build_run(school=self.school, from_year=2026, to_year=2027)
        apply_run(run, user=self.admin)
        revert_run(run, user=self.admin)
        current = AcademicYear.objects.filter(school=self.school, is_current=True).first()
        self.assertIsNotNone(current)
        self.assertEqual(current.year, 2026)

    def test_a_draft_cannot_be_reverted(self):
        make_learner(self.school, grade=5)
        run = build_run(school=self.school, from_year=2026, to_year=2027)
        with self.assertRaises(ValueError):
            revert_run(run, user=self.admin)

    def test_a_reverted_run_cannot_be_reverted_again(self):
        make_learner(self.school, grade=5)
        run = build_run(school=self.school, from_year=2026, to_year=2027)
        apply_run(run, user=self.admin)
        revert_run(run, user=self.admin)
        with self.assertRaises(ValueError):
            revert_run(run, user=self.admin)

    def test_a_whole_school_round_trip_leaves_no_trace(self):
        learners = [make_learner(self.school, grade=g) for g in range(1, 13)]
        before = [(l.id, l.grade, l.active, l.status) for l in learners]
        run = build_run(school=self.school, from_year=2026, to_year=2027)
        run.outcomes.filter(to_grade=10).update(pathway=Pathway.objects.get(code="STEM"))
        apply_run(run, user=self.admin)
        revert_run(run, user=self.admin)
        after = [
            (l.id, l.grade, l.active, l.status)
            for l in Learner.objects.filter(id__in=[l.id for l in learners]).order_by("id")
        ]
        self.assertEqual(sorted(before), sorted(after))


class PromotionApiTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        self.teacher = make_teacher(self.school)
        pathways()
        make_learner(self.school, grade=6)
        self.client.force_authenticate(self.admin)

    def _preview(self, **extra):
        return self.client.post(
            "/api/promotions/runs/",
            {"from_year": 2026, "to_year": 2027, **extra},
            format="json",
        )

    def test_preview_then_apply(self):
        preview = self._preview()
        self.assertEqual(preview.status_code, 201, preview.data)
        run_id = preview.data["id"]
        self.assertEqual(preview.data["summary"]["total"], 1)

        applied = self.client.post(f"/api/promotions/runs/{run_id}/apply/", {}, format="json")
        self.assertEqual(applied.status_code, 200)
        self.assertEqual(applied.data["status"], "APPLIED")

    def test_a_teacher_cannot_run_promotions(self):
        self.client.force_authenticate(self.teacher.user)
        self.assertEqual(self._preview().status_code, 403)

    def test_a_teacher_cannot_apply(self):
        run_id = self._preview().data["id"]
        self.client.force_authenticate(self.teacher.user)
        res = self.client.post(f"/api/promotions/runs/{run_id}/apply/", {}, format="json")
        self.assertEqual(res.status_code, 403)

    def test_only_one_draft_at_a_time(self):
        self._preview()
        second = self._preview()
        self.assertEqual(second.status_code, 400)

    def test_the_new_year_must_follow_the_old_one(self):
        res = self._preview(to_year=2025)
        self.assertEqual(res.status_code, 400)

    def test_grade_ten_without_a_pathway_blocks_the_run(self):
        make_learner(self.school, grade=9)  # no marks, so no proposal
        run_id = self._preview().data["id"]
        res = self.client.post(f"/api/promotions/runs/{run_id}/apply/", {}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("pathway", res.data["detail"])

    def test_an_outcome_can_be_changed_while_the_run_is_a_draft(self):
        run_id = self._preview().data["id"]
        outcome = PromotionOutcome.objects.get(run_id=run_id)
        res = self.client.patch(
            f"/api/promotions/outcomes/{outcome.id}/", {"action": "REPEAT"}, format="json"
        )
        self.assertEqual(res.status_code, 200)
        outcome.refresh_from_db()
        self.assertEqual(outcome.action, "REPEAT")

    def test_an_outcome_is_frozen_once_applied(self):
        run_id = self._preview().data["id"]
        self.client.post(f"/api/promotions/runs/{run_id}/apply/", {}, format="json")
        outcome = PromotionOutcome.objects.get(run_id=run_id)
        res = self.client.patch(
            f"/api/promotions/outcomes/{outcome.id}/", {"action": "REPEAT"}, format="json"
        )
        self.assertEqual(res.status_code, 403)

    def test_an_applied_run_cannot_be_deleted(self):
        run_id = self._preview().data["id"]
        self.client.post(f"/api/promotions/runs/{run_id}/apply/", {}, format="json")
        res = self.client.delete(f"/api/promotions/runs/{run_id}/")
        self.assertEqual(res.status_code, 403)

    def test_a_draft_can_be_discarded(self):
        run_id = self._preview().data["id"]
        self.assertEqual(self.client.delete(f"/api/promotions/runs/{run_id}/").status_code, 204)
        self.assertFalse(PromotionRun.objects.filter(pk=run_id).exists())

    def test_runs_are_scoped_to_the_school(self):
        self._preview()
        other_admin = make_user(make_school("Elsewhere"), "ADMIN")
        self.client.force_authenticate(other_admin)
        self.assertEqual(self.client.get("/api/promotions/runs/").data["count"], 0)

    def test_transitions_endpoint_serves_the_canon(self):
        res = self.client.get("/api/promotions/transitions/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data["pathways"]), 3)
        self.assertTrue(any(t["selects_pathway"] for t in res.data["transitions"]))
