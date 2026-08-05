"""Role boundaries: who may write staff records, and what a parent can see."""

from rest_framework.test import APITestCase

from apps.students.models import ClassGroup
from tests.factories import (
    make_guardian,
    make_learner,
    make_school,
    make_support,
    make_teacher,
    make_user,
)


class AdminOnlyWriteTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        self.teacher = make_teacher(self.school)
        self.support = make_support(self.school)

    def test_teacher_cannot_create_support_staff(self):
        self.client.force_authenticate(self.teacher.user)
        res = self.client.post(
            "/api/support-staff/",
            {"full_name": "Sneaky Hire", "category": "KITCHEN"},
            format="json",
        )
        self.assertEqual(res.status_code, 403)

    def test_teacher_cannot_add_a_teacher(self):
        self.client.force_authenticate(self.teacher.user)
        res = self.client.post(
            "/api/school/staff/add-teacher/",
            {
                "first_name": "New",
                "last_name": "Teacher",
                "tsc_number": "TSC999999",
                "employment_type": "TSC",
            },
            format="json",
        )
        self.assertEqual(res.status_code, 403)

    def test_teacher_cannot_edit_a_teacher(self):
        self.client.force_authenticate(self.teacher.user)
        res = self.client.patch(
            f"/api/school/staff/teachers/{self.teacher.id}/", {"rank": "HEAD"}, format="json"
        )
        self.assertEqual(res.status_code, 403)
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.rank, "TEACHER")

    def test_teacher_cannot_promote_themselves(self):
        """Rank decides how much of the school a login can see, so self-service
        promotion would be a whole-school data leak."""
        self.client.force_authenticate(self.teacher.user)
        res = self.client.patch(
            f"/api/teachers/{self.teacher.id}/", {"rank": "HEAD"}, format="json"
        )
        self.assertEqual(res.status_code, 403)
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.rank, "TEACHER")

    def test_teacher_cannot_reassign_their_own_supervisor(self):
        self.client.force_authenticate(self.teacher.user)
        res = self.client.patch(
            f"/api/teachers/{self.teacher.id}/",
            {"supervisor": self.teacher.user_id},
            format="json",
        )
        self.assertEqual(res.status_code, 403)

    def test_teacher_cannot_add_a_staff_column(self):
        self.client.force_authenticate(self.teacher.user)
        res = self.client.post("/api/staff-fields/", {"label": "NSSF No"}, format="json")
        self.assertEqual(res.status_code, 403)

    def test_admin_can_do_all_of_the_above(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(
            self.client.post(
                "/api/support-staff/",
                {"full_name": "Real Hire", "category": "KITCHEN"},
                format="json",
            ).status_code,
            201,
        )
        self.assertEqual(
            self.client.post("/api/staff-fields/", {"label": "NSSF No"}, format="json").status_code,
            201,
        )

    def test_deleting_support_staff_deactivates_instead(self):
        self.client.force_authenticate(self.admin)
        res = self.client.delete(f"/api/support-staff/{self.support.id}/")
        self.assertEqual(res.status_code, 204)
        self.support.refresh_from_db()
        self.assertFalse(self.support.active)

    def test_added_column_gets_a_stable_key(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post("/api/staff-fields/", {"label": "ID Number"}, format="json")
        self.assertEqual(res.data["key"], "id_number")
        # A second field with the same label must not collide.
        res2 = self.client.post("/api/staff-fields/", {"label": "ID Number"}, format="json")
        self.assertEqual(res2.data["key"], "id_number_2")


class ParentIsolationTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.parent_user = make_user(self.school, "PARENT")
        self.my_child = make_learner(self.school, grade=5)
        self.other_child = make_learner(self.school, grade=5)
        make_guardian(self.school, learners=[self.my_child], user=self.parent_user)

    def test_parent_sees_only_their_own_child_profile(self):
        self.client.force_authenticate(self.parent_user)
        mine = self.client.get(f"/api/learners/{self.my_child.id}/profile/")
        theirs = self.client.get(f"/api/learners/{self.other_child.id}/profile/")
        self.assertEqual(mine.status_code, 200)
        self.assertIn(theirs.status_code, (403, 404))

    def test_parent_cannot_open_the_school_structure(self):
        self.client.force_authenticate(self.parent_user)
        self.assertEqual(self.client.get("/api/school/structure/").status_code, 403)
        self.assertEqual(self.client.get("/api/school/grades/5/").status_code, 403)

    def test_parent_cannot_read_the_staff_directory(self):
        self.client.force_authenticate(self.parent_user)
        self.assertEqual(self.client.get("/api/school/staff/").status_code, 403)

    def test_parent_summary_returns_only_their_children(self):
        self.client.force_authenticate(self.parent_user)
        res = self.client.get("/api/parent/summary/")
        self.assertEqual(res.status_code, 200)
        ids = [c["id"] for c in res.data["children"]]
        self.assertEqual(ids, [self.my_child.id])

    def test_parent_has_no_staff_portal(self):
        self.client.force_authenticate(self.parent_user)
        self.assertEqual(self.client.get("/api/my-portal/").status_code, 403)


class AnonymousTests(APITestCase):
    def test_api_requires_authentication(self):
        for path in ("/api/learners/", "/api/school/staff/", "/api/my-portal/", "/api/my-team/"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 401)


class ClassTeacherTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        self.teacher = make_teacher(self.school)
        ClassGroup.objects.create(school=self.school, grade=5, stream="North",
                                  class_teacher=self.teacher)
        for _ in range(3):
            make_learner(self.school, grade=5, stream="North")

    def test_grade_detail_reports_the_class_teacher_and_roll(self):
        self.client.force_authenticate(self.admin)
        res = self.client.get("/api/school/grades/5/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data["students"]), 3)
        names = [ct["name"] for ct in res.data["class_teachers"]]
        self.assertIn(self.teacher.user.get_full_name(), names)
