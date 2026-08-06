"""Write guards on every endpoint a signed-in user can reach.

The audit that produced this file found viewsets registered with full CRUD and
no role check. On a shared-table multi-tenant system the blast radius is large:
LearningArea is national, so deleting one cascades into every school's
assessments and scores.
"""

from rest_framework.test import APITestCase

from apps.assessments.models import LearningArea, Score
from apps.students.models import Pathway
from tests.factories import (
    make_assessment,
    make_guardian,
    make_learner,
    make_learning_area,
    make_school,
    make_teacher,
    make_user,
)


class NationalModelGuardTests(APITestCase):
    """LearningArea and Pathway are shared by every school on the platform."""

    def setUp(self):
        self.school = make_school()
        self.parent = make_user(self.school, "PARENT")
        self.teacher = make_teacher(self.school)
        self.admin = make_user(self.school, "ADMIN")
        self.maths = make_learning_area("Mathematics", "MATH")

    def test_a_parent_cannot_create_a_learning_area(self):
        self.client.force_authenticate(self.parent)
        res = self.client.post(
            "/api/learning-areas/", {"name": "Fake", "code": "FAKE", "grades": []},
            format="json",
        )
        self.assertEqual(res.status_code, 403)

    def test_a_teacher_cannot_delete_a_learning_area(self):
        """Deleting one cascades into every school's assessments and scores."""
        assessment = make_assessment(self.school, learning_area=self.maths, grade=5)
        learner = make_learner(self.school, grade=5)
        Score.objects.create(
            school=self.school, assessment=assessment, learner=learner, marks=70
        )
        self.client.force_authenticate(self.teacher.user)
        res = self.client.delete(f"/api/learning-areas/{self.maths.id}/")
        self.assertEqual(res.status_code, 403)
        self.assertTrue(LearningArea.objects.filter(pk=self.maths.pk).exists())
        self.assertEqual(Score.objects.count(), 1)

    def test_a_parent_cannot_delete_a_pathway(self):
        pathway = Pathway.objects.create(code="STEM")
        self.client.force_authenticate(self.parent)
        res = self.client.delete(f"/api/pathways/{pathway.id}/")
        self.assertEqual(res.status_code, 403)
        self.assertTrue(Pathway.objects.filter(pk=pathway.pk).exists())

    def test_reading_stays_open_to_staff(self):
        self.client.force_authenticate(self.teacher.user)
        self.assertEqual(self.client.get("/api/learning-areas/").status_code, 200)


class SchoolRecordGuardTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.parent = make_user(self.school, "PARENT")
        self.teacher = make_teacher(self.school)

    def test_a_teacher_cannot_edit_the_school_record(self):
        """paybill_account_prefix steers M-Pesa reconciliation — changing it
        redirects how payments match invoices."""
        self.client.force_authenticate(self.teacher.user)
        res = self.client.patch(
            f"/api/schools/{self.school.id}/",
            {"paybill_account_prefix": "EVIL"},
            format="json",
        )
        self.assertEqual(res.status_code, 403)
        self.school.refresh_from_db()
        self.assertNotEqual(self.school.paybill_account_prefix, "EVIL")

    def test_a_parent_cannot_rename_the_school(self):
        self.client.force_authenticate(self.parent)
        res = self.client.patch(
            f"/api/schools/{self.school.id}/", {"name": "Renamed"}, format="json"
        )
        self.assertEqual(res.status_code, 403)


class GuardianPrivacyTests(APITestCase):
    """The guardian register is every family's name and phone number."""

    def setUp(self):
        self.school = make_school()
        self.parent = make_user(self.school, "PARENT")
        child = make_learner(self.school)
        make_guardian(self.school, learners=[child], user=self.parent)
        # Another family's contact details.
        make_guardian(self.school, learners=[make_learner(self.school)])

    def test_a_parent_cannot_list_the_guardian_register(self):
        self.client.force_authenticate(self.parent)
        res = self.client.get("/api/guardians/")
        self.assertEqual(res.status_code, 403)

    def test_staff_still_can(self):
        teacher = make_teacher(self.school)
        self.client.force_authenticate(teacher.user)
        res = self.client.get("/api/guardians/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["count"], 2)


class TimetableGuardTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.parent = make_user(self.school, "PARENT")
        self.admin = make_user(self.school, "ADMIN")

    def test_a_parent_cannot_create_rooms_or_periods(self):
        self.client.force_authenticate(self.parent)
        self.assertEqual(
            self.client.post("/api/timetable/rooms/", {"name": "X"}, format="json").status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/timetable/periods/",
                {"number": 1, "start_time": "08:00", "end_time": "08:40"},
                format="json",
            ).status_code,
            403,
        )

    def test_the_admin_still_can(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(
            self.client.post("/api/timetable/rooms/", {"name": "Lab"}, format="json").status_code,
            201,
        )


class AnnouncementGuardTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.parent = make_user(self.school, "PARENT")
        self.admin = make_user(self.school, "ADMIN")

    def test_a_parent_cannot_publish_an_announcement(self):
        """An announcement reaches every parent, optionally by SMS blast."""
        self.client.force_authenticate(self.parent)
        res = self.client.post(
            "/api/communication/announcements/",
            {"title": "School closed", "body": "Fake notice", "audience": "PARENTS"},
            format="json",
        )
        self.assertEqual(res.status_code, 403)

    def test_a_parent_cannot_send_sms(self):
        self.client.force_authenticate(self.parent)
        res = self.client.post(
            "/api/communication/sms/",
            {"recipient": "254700000001", "body": "spam"},
            format="json",
        )
        self.assertEqual(res.status_code, 403)

    def test_the_admin_still_can_announce(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            "/api/communication/announcements/",
            {"title": "Real notice", "body": "Term dates", "audience": "ALL"},
            format="json",
        )
        self.assertEqual(res.status_code, 201)


class GeneratorGuardTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.parent = make_user(self.school, "PARENT")
        self.admin = make_user(self.school, "ADMIN")

    def test_a_parent_cannot_regenerate_the_timetable(self):
        """The generator replaces every lesson in the school."""
        self.client.force_authenticate(self.parent)
        res = self.client.post("/api/timetable/generate/", {}, format="json")
        self.assertEqual(res.status_code, 403)

    def test_a_parent_cannot_queue_class_report_cards(self):
        self.client.force_authenticate(self.parent)
        res = self.client.post(
            "/api/report-cards/generate-class/",
            {"grade": 5, "stream": "", "term": 1, "year": 2026},
            format="json",
        )
        self.assertEqual(res.status_code, 403)

    def test_the_admin_still_regenerates(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post("/api/timetable/generate/", {}, format="json")
        self.assertEqual(res.status_code, 200)

