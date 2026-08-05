"""Multi-tenancy: a user must never read or write another school's rows.

These are the tests that matter most — every other feature is built on the
assumption that `school` scoping holds.
"""

from rest_framework.test import APITestCase

from apps.teachers.models import StaffMessage, StaffReport, StaffTask
from tests.factories import (
    make_learner,
    make_school,
    make_support,
    make_teacher,
    make_user,
)


class TenancyTests(APITestCase):
    def setUp(self):
        self.school_a = make_school("School A")
        self.school_b = make_school("School B")

        self.admin_a = make_user(self.school_a, "ADMIN", username="admin_a")
        self.admin_b = make_user(self.school_b, "ADMIN", username="admin_b")

        self.learner_a = make_learner(self.school_a)
        self.learner_b = make_learner(self.school_b)

        self.head_b = make_teacher(self.school_b, rank="HEAD")
        self.cook_b = make_support(self.school_b, supervisor=self.head_b.user)

    def test_learner_list_is_scoped(self):
        self.client.force_authenticate(self.admin_a)
        res = self.client.get("/api/learners/")
        ids = [row["id"] for row in res.data["results"]]
        self.assertIn(self.learner_a.id, ids)
        self.assertNotIn(self.learner_b.id, ids)

    def test_learner_detail_from_other_school_is_404(self):
        self.client.force_authenticate(self.admin_a)
        res = self.client.get(f"/api/learners/{self.learner_b.id}/")
        self.assertEqual(res.status_code, 404)

    def test_learner_write_to_other_school_is_404(self):
        self.client.force_authenticate(self.admin_a)
        res = self.client.patch(
            f"/api/learners/{self.learner_b.id}/", {"first_name": "Hacked"}, format="json"
        )
        self.assertEqual(res.status_code, 404)
        self.learner_b.refresh_from_db()
        self.assertNotEqual(self.learner_b.first_name, "Hacked")

    def test_support_staff_list_is_scoped(self):
        self.client.force_authenticate(self.admin_a)
        res = self.client.get("/api/support-staff/")
        self.assertEqual(res.data["count"], 0)

    def test_staff_directory_is_scoped(self):
        self.client.force_authenticate(self.admin_a)
        res = self.client.get("/api/school/staff/")
        self.assertEqual(res.data["totals"]["teaching"], 0)
        self.assertEqual(res.data["totals"]["non_teaching"], 0)

    def test_admin_cannot_drill_into_another_schools_staff(self):
        """An ADMIN's rank is school-wide, but must stop at the school border."""
        self.client.force_authenticate(self.admin_a)
        res = self.client.get(f"/api/my-team/{self.cook_b.user_id}/")
        self.assertIn(res.status_code, (403, 404))

    def test_admin_cannot_assign_work_across_schools(self):
        self.client.force_authenticate(self.admin_a)
        res = self.client.post(
            "/api/staff-tasks/",
            {"assigned_to": self.cook_b.user_id, "title": "Cross-tenant task"},
            format="json",
        )
        self.assertIn(res.status_code, (400, 403))
        self.assertFalse(StaffTask.objects.filter(title="Cross-tenant task").exists())

    def test_admin_cannot_message_across_schools(self):
        self.client.force_authenticate(self.admin_a)
        res = self.client.post(
            "/api/staff-messages/",
            {"recipient": self.cook_b.user_id, "body": "hello from another school"},
            format="json",
        )
        self.assertIn(res.status_code, (400, 403))
        self.assertEqual(StaffMessage.objects.count(), 0)

    def test_report_list_is_scoped(self):
        StaffReport.objects.create(
            school=self.school_b, author=self.cook_b.user, title="B report"
        )
        self.client.force_authenticate(self.admin_a)
        res = self.client.get("/api/staff-reports/")
        self.assertEqual(res.data["count"], 0)

    def test_grade_detail_is_scoped(self):
        make_learner(self.school_b, grade=5)
        self.client.force_authenticate(self.admin_a)
        res = self.client.get("/api/school/grades/5/")
        adm = [s["admission_number"] for s in res.data["students"]]
        self.assertNotIn(self.learner_b.admission_number, adm)
