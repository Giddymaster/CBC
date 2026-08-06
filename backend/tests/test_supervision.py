"""Rank-based visibility, task assignment and messaging between staff."""

from rest_framework.test import APITestCase

from apps.teachers.models import StaffMessage, StaffReport, StaffTask
from apps.teachers.supervision import rank_level, visible_staff_ids
from tests.factories import make_school, make_support, make_teacher


class SupervisionScopeTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        # head -> senior -> teacher ; head -> cook_boss -> cook
        self.head = make_teacher(self.school, rank="HEAD")
        self.senior = make_teacher(self.school, rank="SENIOR", supervisor=self.head.user)
        self.teacher = make_teacher(
            self.school, rank="TEACHER", supervisor=self.senior.user
        )
        self.cook_boss = make_support(
            self.school, category="KITCHEN", supervisor=self.head.user
        )
        self.cook = make_support(
            self.school, category="KITCHEN", supervisor=self.cook_boss.user
        )
        self.cleaner = make_support(self.school, category="CLEANER", supervisor=self.head.user)

    def test_head_sees_whole_school(self):
        ids = visible_staff_ids(self.head.user)
        self.assertEqual(
            ids,
            {
                self.senior.user_id,
                self.teacher.user_id,
                self.cook_boss.user_id,
                self.cook.user_id,
                self.cleaner.user_id,
            },
        )

    def test_senior_sees_own_subtree_only(self):
        ids = visible_staff_ids(self.senior.user)
        self.assertEqual(ids, {self.teacher.user_id})

    def test_supervising_support_staff_gets_section_head_reach(self):
        self.assertEqual(rank_level(self.cook_boss.user), 3)
        self.assertEqual(visible_staff_ids(self.cook_boss.user), {self.cook.user_id})

    def test_plain_staff_see_nobody(self):
        self.assertEqual(rank_level(self.cook.user), 1)
        self.assertEqual(visible_staff_ids(self.cook.user), set())

    def test_supervisor_cycle_does_not_hang(self):
        """A mis-entered reporting line must not spin forever."""
        self.senior.supervisor = self.teacher.user
        self.senior.save()
        ids = visible_staff_ids(self.senior.user)
        self.assertIn(self.teacher.user_id, ids)
        self.assertNotIn(self.senior.user_id, ids)

    def test_my_team_groups_by_category(self):
        self.client.force_authenticate(self.head.user)
        res = self.client.get("/api/my-team/")
        self.assertEqual(res.status_code, 200)
        by_cat = {g["category"]: len(g["staff"]) for g in res.data["groups"]}
        self.assertEqual(by_cat["Teaching staff"], 2)
        self.assertEqual(by_cat["Kitchen staff"], 2)
        self.assertEqual(by_cat["Cleaner"], 1)
        self.assertEqual(res.data["total"], 5)

    def test_team_list_marks_direct_reports(self):
        self.client.force_authenticate(self.head.user)
        res = self.client.get("/api/my-team/")
        flat = {p["id"]: p["direct"] for g in res.data["groups"] for p in g["staff"]}
        self.assertTrue(flat[self.senior.user_id])
        self.assertFalse(flat[self.teacher.user_id])


class TaskAndMessageTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.head = make_teacher(self.school, rank="HEAD")
        self.boss = make_support(self.school, category="KITCHEN", supervisor=self.head.user)
        self.cook = make_support(self.school, category="KITCHEN", supervisor=self.boss.user)
        self.cleaner = make_support(self.school, category="CLEANER", supervisor=self.head.user)

    def test_supervisor_can_assign_work(self):
        self.client.force_authenticate(self.boss.user)
        res = self.client.post(
            "/api/staff-tasks/",
            {"assigned_to": self.cook.user_id, "title": "Deep clean the store"},
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(StaffTask.objects.get().assigned_by_id, self.boss.user_id)

    def test_cannot_assign_outside_your_line(self):
        self.client.force_authenticate(self.cleaner.user)
        res = self.client.post(
            "/api/staff-tasks/",
            {"assigned_to": self.cook.user_id, "title": "Not mine to give"},
            format="json",
        )
        self.assertEqual(res.status_code, 403)

    def test_assignee_can_update_status(self):
        task = StaffTask.objects.create(
            school=self.school,
            assigned_to=self.cook.user,
            assigned_by=self.boss.user,
            title="Wash the pots",
        )
        self.client.force_authenticate(self.cook.user)
        res = self.client.patch(f"/api/staff-tasks/{task.id}/", {"status": "DONE"}, format="json")
        self.assertEqual(res.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.status, "DONE")
        self.assertIsNotNone(task.completed_at)

    def test_assignee_cannot_reassign_or_rewrite_the_task(self):
        task = StaffTask.objects.create(
            school=self.school,
            assigned_to=self.cook.user,
            assigned_by=self.boss.user,
            title="Wash the pots",
        )
        self.client.force_authenticate(self.cook.user)
        self.client.patch(
            f"/api/staff-tasks/{task.id}/",
            {"assigned_to": self.cleaner.user_id, "title": "Something easier"},
            format="json",
        )
        task.refresh_from_db()
        self.assertEqual(task.assigned_to_id, self.cook.user_id)
        self.assertEqual(task.title, "Wash the pots")

    def test_unrelated_staff_cannot_see_the_task(self):
        StaffTask.objects.create(
            school=self.school,
            assigned_to=self.cook.user,
            assigned_by=self.boss.user,
            title="Private work",
        )
        self.client.force_authenticate(self.cleaner.user)
        res = self.client.get("/api/staff-tasks/")
        self.assertEqual(res.data["count"], 0)

    def test_staff_may_message_their_own_supervisor(self):
        self.client.force_authenticate(self.cook.user)
        res = self.client.post(
            "/api/staff-messages/",
            {"recipient": self.boss.user_id, "body": "Beans arriving Monday"},
            format="json",
        )
        self.assertEqual(res.status_code, 201)

    def test_staff_may_not_message_a_stranger(self):
        self.client.force_authenticate(self.cook.user)
        res = self.client.post(
            "/api/staff-messages/",
            {"recipient": self.cleaner.user_id, "body": "hi"},
            format="json",
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(StaffMessage.objects.count(), 0)

    def test_message_thread_filter_rejects_junk(self):
        self.client.force_authenticate(self.cook.user)
        res = self.client.get("/api/staff-messages/?with=not-a-number")
        self.assertEqual(res.status_code, 400)

    def test_drill_down_blocked_outside_your_line(self):
        self.client.force_authenticate(self.cleaner.user)
        res = self.client.get(f"/api/my-team/{self.cook.user_id}/")
        self.assertEqual(res.status_code, 403)

    def test_drill_down_shows_reports_tasks_and_thread(self):
        StaffReport.objects.create(
            school=self.school,
            author=self.cook.user,
            supervisor=self.boss.user,
            title="Weekly kitchen report",
            status=StaffReport.Status.SUBMITTED,
        )
        StaffTask.objects.create(
            school=self.school,
            assigned_to=self.cook.user,
            assigned_by=self.boss.user,
            title="Order flour",
        )
        StaffMessage.objects.create(
            school=self.school, sender=self.cook.user, recipient=self.boss.user, body="Done"
        )
        self.client.force_authenticate(self.boss.user)
        res = self.client.get(f"/api/my-team/{self.cook.user_id}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["category"], "Kitchen staff")
        self.assertEqual(len(res.data["reports"]), 1)
        self.assertEqual(len(res.data["tasks"]), 1)
        self.assertEqual(len(res.data["messages"]), 1)

    def test_reading_a_thread_marks_it_read(self):
        msg = StaffMessage.objects.create(
            school=self.school, sender=self.cook.user, recipient=self.boss.user, body="Done"
        )
        self.client.force_authenticate(self.boss.user)
        self.client.get(f"/api/my-team/{self.cook.user_id}/")
        msg.refresh_from_db()
        self.assertIsNotNone(msg.read_at)


class ReportApprovalTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.head = make_teacher(self.school, rank="HEAD")
        self.cook = make_support(self.school, category="KITCHEN", supervisor=self.head.user)
        self.other = make_support(self.school, category="CLEANER", supervisor=self.head.user)

    def _submitted_report(self):
        return StaffReport.objects.create(
            school=self.school,
            author=self.cook.user,
            supervisor=self.head.user,
            title="Kitchen weekly",
            status=StaffReport.Status.SUBMITTED,
        )

    def test_supervisor_approves(self):
        report = self._submitted_report()
        self.client.force_authenticate(self.head.user)
        res = self.client.post(
            f"/api/staff-reports/{report.id}/review/",
            {"decision": "approve", "comment": "Good work"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        report.refresh_from_db()
        self.assertEqual(report.status, "APPROVED")
        self.assertEqual(report.reviewed_by_id, self.head.user_id)

    def test_peer_cannot_review(self):
        report = self._submitted_report()
        self.client.force_authenticate(self.other.user)
        res = self.client.post(
            f"/api/staff-reports/{report.id}/review/", {"decision": "approve"}, format="json"
        )
        self.assertIn(res.status_code, (403, 404))

    def test_author_cannot_edit_after_approval(self):
        report = self._submitted_report()
        report.status = StaffReport.Status.APPROVED
        report.save()
        self.client.force_authenticate(self.cook.user)
        res = self.client.patch(
            f"/api/staff-reports/{report.id}/", {"title": "Changed"}, format="json"
        )
        self.assertEqual(res.status_code, 403)

    def test_submitting_without_a_supervisor_is_rejected(self):
        orphan = make_support(self.school, category="OTHER")
        report = StaffReport.objects.create(
            school=self.school, author=orphan.user, title="Nowhere to go"
        )
        self.client.force_authenticate(orphan.user)
        res = self.client.post(f"/api/staff-reports/{report.id}/submit/", {}, format="json")
        self.assertEqual(res.status_code, 400)
