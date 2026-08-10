"""Scheme-of-work workflow (upload / generate / review) and the facilities tree."""

from rest_framework.test import APITestCase

from apps.facilities.models import Facility, FacilityCategory, NavSection, Supply
from apps.teachers.models import SchemeOfWork
from apps.timetable.models import LessonRequirement
from tests.factories import (
    make_learning_area,
    make_school,
    make_support,
    make_teacher,
    make_user,
)


class SchemeWorkflowTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        self.teacher = make_teacher(self.school)
        self.maths = make_learning_area("Mathematics", "MATH")
        self.music = make_learning_area("Music", "MUS")
        LessonRequirement.objects.create(
            school=self.school, teacher=self.teacher, learning_area=self.maths,
            grade=5, stream="North",
        )

    def test_teacher_can_create_a_scheme_for_a_subject_they_teach(self):
        self.client.force_authenticate(self.teacher.user)
        res = self.client.post(
            "/api/schemes-of-work/",
            {"learning_area": self.maths.id, "grade": 5, "term": 1, "year": 2026},
            format="json",
        )
        self.assertEqual(res.status_code, 201)

    def test_teacher_cannot_create_a_scheme_for_a_subject_they_do_not_teach(self):
        self.client.force_authenticate(self.teacher.user)
        res = self.client.post(
            "/api/schemes-of-work/",
            {"learning_area": self.music.id, "grade": 5, "term": 1, "year": 2026},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertFalse(SchemeOfWork.objects.filter(learning_area=self.music).exists())

    def test_generated_scheme_lands_as_a_draft_to_proofread(self):
        """A machine draft is a starting point: the teacher reads and edits it
        before the head teacher ever sees it."""
        self.client.force_authenticate(self.teacher.user)
        res = self.client.post(
            "/api/schemes-of-work/generate/",
            {"learning_area": self.maths.id, "grade": 5, "term": 1, "year": 2026, "weeks": 3},
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        scheme = SchemeOfWork.objects.get(pk=res.data["id"])
        self.assertEqual(scheme.status, "DRAFT")
        self.assertEqual(scheme.source, "GENERATED")
        self.assertTrue(scheme.content)

    def test_the_teacher_edits_the_draft_then_submits_it(self):
        self.client.force_authenticate(self.teacher.user)
        scheme = SchemeOfWork.objects.create(
            school=self.school, teacher=self.teacher, learning_area=self.maths,
            grade=5, term=1, year=2026, status="DRAFT",
            content={"weeks": [{"week": 1, "lessons": [{"lesson": 1, "strand": "Old"}]}]},
        )
        edited = self.client.patch(
            f"/api/schemes-of-work/{scheme.id}/",
            {"content": {"weeks": [{"week": 1, "lessons": [
                {"lesson": 1, "strand": "Numbers", "sub_strand": "Place value"}]}]}},
            format="json",
        )
        self.assertEqual(edited.status_code, 200, edited.data)
        scheme.refresh_from_db()
        self.assertEqual(scheme.content["weeks"][0]["lessons"][0]["strand"], "Numbers")

        sent = self.client.post(f"/api/schemes-of-work/submit/{scheme.id}/", {},
                                format="json")
        self.assertEqual(sent.status_code, 200, sent.data)
        scheme.refresh_from_db()
        self.assertEqual(scheme.status, "PENDING")

    def test_an_approved_scheme_is_not_quietly_rewritten(self):
        scheme = SchemeOfWork.objects.create(
            school=self.school, teacher=self.teacher, learning_area=self.maths,
            grade=5, term=1, year=2026, status="APPROVED",
        )
        self.client.force_authenticate(self.teacher.user)
        res = self.client.patch(
            f"/api/schemes-of-work/{scheme.id}/", {"content": {"weeks": []}},
            format="json",
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn("approved", res.data["detail"].lower())

    def test_a_teacher_cannot_edit_someone_elses_scheme(self):
        from tests.factories import make_teacher

        other = make_teacher(self.school)
        scheme = SchemeOfWork.objects.create(
            school=self.school, teacher=other, learning_area=self.maths,
            grade=5, term=1, year=2026, status="DRAFT",
        )
        self.client.force_authenticate(self.teacher.user)
        res = self.client.patch(
            f"/api/schemes-of-work/{scheme.id}/", {"content": {"weeks": []}},
            format="json",
        )
        self.assertIn(res.status_code, (403, 404))

    def test_only_an_admin_may_review(self):
        scheme = SchemeOfWork.objects.create(
            school=self.school, teacher=self.teacher, learning_area=self.maths,
            grade=5, term=1, year=2026, status="PENDING",
        )
        self.client.force_authenticate(self.teacher.user)
        denied = self.client.post(
            f"/api/schemes-of-work/{scheme.id}/review/",
            {"decision": "approve"},
            format="json",
        )
        self.assertEqual(denied.status_code, 403)

        self.client.force_authenticate(self.admin)
        allowed = self.client.post(
            f"/api/schemes-of-work/{scheme.id}/review/",
            {"decision": "approve", "comment": "Well structured"},
            format="json",
        )
        self.assertEqual(allowed.status_code, 200)
        scheme.refresh_from_db()
        self.assertEqual(scheme.status, "APPROVED")
        self.assertEqual(scheme.reviewed_by_id, self.admin.id)

    def test_a_teacher_sees_only_their_own_schemes(self):
        other = make_teacher(self.school)
        SchemeOfWork.objects.create(
            school=self.school, teacher=other, learning_area=self.maths,
            grade=5, term=1, year=2026,
        )
        self.client.force_authenticate(self.teacher.user)
        res = self.client.get("/api/schemes-of-work/")
        self.assertEqual(res.data["count"], 0)


class FacilityTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        self.section = NavSection.objects.create(school=self.school, name="Facilities")
        self.category = FacilityCategory.objects.create(
            school=self.school, name="Dormitories", section=self.section
        )
        self.facility = Facility.objects.create(
            school=self.school, name="Kilimanjaro House", category=self.category, capacity=60
        )

    def test_supply_status_tracks_stock(self):
        depleted = Supply.objects.create(
            school=self.school, facility=self.facility, item="Blankets",
            quantity=0, reorder_level=10,
        )
        low = Supply.objects.create(
            school=self.school, facility=self.facility, item="Mattresses",
            quantity=5, reorder_level=10,
        )
        ok = Supply.objects.create(
            school=self.school, facility=self.facility, item="Buckets",
            quantity=50, reorder_level=10,
        )
        self.assertEqual(depleted.status, "DEPLETED")
        self.assertEqual(low.status, "LOW")
        self.assertEqual(ok.status, "IN_STOCK")

    def test_admin_can_add_a_category_and_a_section(self):
        self.client.force_authenticate(self.admin)
        section = self.client.post("/api/nav-sections/", {"name": "Welfare"}, format="json")
        self.assertEqual(section.status_code, 201)
        category = self.client.post(
            "/api/facility-categories/",
            {"name": "Counselling rooms", "section": section.data["id"]},
            format="json",
        )
        self.assertEqual(category.status_code, 201)

    def test_facilities_are_scoped_to_the_school(self):
        other_school = make_school("Elsewhere")
        other_section = NavSection.objects.create(school=other_school, name="Facilities")
        other_category = FacilityCategory.objects.create(
            school=other_school, name="Dormitories", section=other_section
        )
        Facility.objects.create(
            school=other_school, name="Their House", category=other_category
        )
        self.client.force_authenticate(self.admin)
        res = self.client.get("/api/facilities/")
        names = [f["name"] for f in res.data["results"]]
        self.assertEqual(names, ["Kilimanjaro House"])

    def test_assigning_staff_to_a_facility(self):
        cook = make_support(self.school, category="KITCHEN")
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            "/api/facility-assignments/",
            {"facility": self.facility.id, "support_staff": cook.id, "position": "Matron"},
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["position"], "Matron")
