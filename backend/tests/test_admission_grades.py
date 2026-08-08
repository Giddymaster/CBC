"""Admission rights scoped to specific grades."""

from rest_framework.test import APITestCase

from apps.students.models import AdmissionRight, Learner
from tests.factories import make_school, make_teacher, make_user


def grant(school, user, grades):
    return AdmissionRight.objects.create(school=school, user=user, grades=grades)


def admission_form(grade):
    return {
        "first_name": "Test", "last_name": "Child",
        "date_of_birth": "2018-03-04", "gender": "F", "grade": grade,
    }


class GradeScopedAdmissionTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        self.teacher = make_teacher(self.school)

    def test_a_grade_scoped_grant_admits_into_its_grades(self):
        grant(self.school, self.teacher.user, [1, 2])
        self.client.force_authenticate(self.teacher.user)
        res = self.client.post("/api/admissions/", admission_form(1), format="json")
        self.assertEqual(res.status_code, 201, res.data)

    def test_and_not_into_others(self):
        grant(self.school, self.teacher.user, [1])
        self.client.force_authenticate(self.teacher.user)
        res = self.client.post("/api/admissions/", admission_form(7), format="json")
        self.assertEqual(res.status_code, 403)
        self.assertIn("Grade 1", res.data["detail"])
        self.assertFalse(Learner.objects.exists())

    def test_an_unrestricted_grant_still_covers_every_grade(self):
        grant(self.school, self.teacher.user, [])
        self.client.force_authenticate(self.teacher.user)
        res = self.client.post("/api/admissions/", admission_form(9), format="json")
        self.assertEqual(res.status_code, 201, res.data)

    def test_the_admin_is_never_restricted(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post("/api/admissions/", admission_form(12), format="json")
        self.assertEqual(res.status_code, 201, res.data)

    def test_access_reports_the_allowed_grades(self):
        grant(self.school, self.teacher.user, [1, 2])
        self.client.force_authenticate(self.teacher.user)
        self.assertEqual(
            self.client.get("/api/admissions/access/").data["grades"], [1, 2]
        )
        self.client.force_authenticate(self.admin)
        self.assertIsNone(self.client.get("/api/admissions/access/").data["grades"])

    def test_bulk_import_drops_out_of_scope_rows(self):
        import io

        grant(self.school, self.teacher.user, [1])
        csv_data = (
            "first name,last name,date of birth,gender,grade,guardian,guardian phone\n"
            "Amina,Yusuf,2019-01-01,F,1,Mama Amina,254700000001\n"
            "Brian,Otieno,2013-01-01,M,7,Mama Brian,254700000002\n"
        )
        self.client.force_authenticate(self.teacher.user)
        res = self.client.post(
            "/api/admissions/bulk/",
            {"file": io.BytesIO(csv_data.encode()), "commit": "true"},
            format="multipart",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["created"], 1)
        self.assertTrue(Learner.objects.filter(first_name="Amina").exists())
        self.assertFalse(Learner.objects.filter(first_name="Brian").exists())
        self.assertTrue(
            any("admission rights" in e["errors"][0] for e in res.data["problems"])
        )
