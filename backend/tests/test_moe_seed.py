"""Seeding the KICD/MoE learning-area canon."""

from rest_framework.test import APITestCase

from apps.assessments.models import LearningArea
from apps.schools.moe import LEARNING_AREAS
from tests.factories import make_learning_area, make_school, make_teacher, make_user


class MoeSeedTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")

    def test_the_canon_lands_with_level_grades(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post("/api/learning-areas/seed-moe/", {}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["created"], len(LEARNING_AREAS))
        maths = LearningArea.objects.get(name="Mathematics")
        self.assertEqual(maths.grades, [4, 5, 6, 7, 8, 9, 10, 11, 12])
        # Junior School carries exactly its nine rationalised areas.
        jss = [a.name for a in LearningArea.objects.all() if 7 in a.grades]
        self.assertEqual(len(jss), 9)
        self.assertIn("Integrated Science", jss)
        self.assertIn("Pre-Technical Studies", jss)

    def test_seeding_twice_changes_nothing(self):
        self.client.force_authenticate(self.admin)
        self.client.post("/api/learning-areas/seed-moe/", {}, format="json")
        res = self.client.post("/api/learning-areas/seed-moe/", {}, format="json")
        self.assertEqual(res.data, {"created": 0, "updated": 0})
        self.assertEqual(LearningArea.objects.count(), len(LEARNING_AREAS))

    def test_an_existing_area_keeps_its_row_and_gains_the_canon_grades(self):
        """A school that already typed 'Mathematics' for G7 only keeps that row
        (and everything hanging off it) — the canon's grades merge in."""
        existing = make_learning_area("Mathematics", "MATH-X", grades=[7])
        self.client.force_authenticate(self.admin)
        res = self.client.post("/api/learning-areas/seed-moe/", {}, format="json")
        self.assertEqual(res.data["created"], len(LEARNING_AREAS) - 1)
        self.assertEqual(res.data["updated"], 1)
        existing.refresh_from_db()
        self.assertEqual(existing.grades, [4, 5, 6, 7, 8, 9, 10, 11, 12])

    def test_a_teacher_cannot_seed(self):
        teacher = make_teacher(self.school)
        self.client.force_authenticate(teacher.user)
        res = self.client.post("/api/learning-areas/seed-moe/", {}, format="json")
        self.assertEqual(res.status_code, 403)
        self.assertEqual(LearningArea.objects.count(), 0)
