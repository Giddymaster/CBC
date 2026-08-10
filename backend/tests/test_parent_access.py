"""Signing in with a child's number, and what the family then sees."""

from decimal import Decimal

from rest_framework.test import APITestCase

from apps.payments.models import FeeStructure, Invoice
from apps.students.models import Guardian
from tests.factories import make_guardian, make_learner, make_school, make_user


class ParentLoginTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.parent = make_user(self.school, "PARENT", username="mama-amina")
        self.parent.set_password("secret-pw")
        self.parent.save()
        self.amina = make_learner(
            self.school, grade=5, admission_number="ADM0081", upi="UPI556677",
        )
        make_guardian(self.school, learners=[self.amina], user=self.parent)

    def _login(self, username, password="secret-pw"):
        return self.client.post(
            "/api/auth/token/", {"username": username, "password": password},
            format="json",
        )

    def test_the_admission_number_signs_the_parent_in(self):
        res = self._login("ADM0081")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertTrue(res.data["token"])
        self.assertEqual(res.data["username"], "mama-amina")
        self.assertEqual(res.data["role"], "PARENT")

    def test_the_upi_works_too_and_is_case_insensitive(self):
        self.assertEqual(self._login("upi556677").status_code, 200)

    def test_the_real_username_still_works(self):
        self.assertEqual(self._login("mama-amina").status_code, 200)

    def test_a_wrong_password_still_fails(self):
        self.assertEqual(self._login("ADM0081", "wrong").status_code, 400)

    def test_an_unknown_number_fails_like_any_bad_credential(self):
        self.assertEqual(self._login("ADM9999").status_code, 400)

    def test_a_child_with_no_guardian_login_cannot_be_used_to_sign_in(self):
        orphaned = make_learner(self.school, grade=4, admission_number="ADM0500")
        make_guardian(self.school, learners=[orphaned])  # guardian, but no account
        self.assertEqual(self._login("ADM0500").status_code, 400)


class CreateParentLoginTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        self.learner = make_learner(
            self.school, grade=5, admission_number="ADM0126",
        )
        self.guardian = make_guardian(self.school, learners=[self.learner])

    def test_the_office_issues_a_login_keyed_to_the_admission_number(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            "/api/parent-logins/", {"learner": self.learner.id}, format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["username"], "adm0126")
        self.assertTrue(res.data["generated_password"])
        self.guardian.refresh_from_db()
        self.assertIsNotNone(self.guardian.user)
        self.assertEqual(self.guardian.user.role, "PARENT")
        self.assertTrue(self.guardian.user.must_change_password)

        # And that login works by admission number straight away.
        self.client.force_authenticate(None)
        signin = self.client.post(
            "/api/auth/token/",
            {"username": "ADM0126", "password": res.data["generated_password"]},
            format="json",
        )
        self.assertEqual(signin.status_code, 200, signin.data)

    def test_a_family_that_already_has_one_is_not_given_another(self):
        self.client.force_authenticate(self.admin)
        self.client.post("/api/parent-logins/", {"learner": self.learner.id},
                         format="json")
        again = self.client.post("/api/parent-logins/", {"learner": self.learner.id},
                                 format="json")
        self.assertFalse(again.data["created"])
        self.assertEqual(Guardian.objects.filter(user__isnull=False).count(), 1)

    def test_only_the_office_issues_parent_logins(self):
        self.client.force_authenticate(make_user(self.school, "TEACHER"))
        res = self.client.post("/api/parent-logins/", {"learner": self.learner.id},
                               format="json")
        self.assertEqual(res.status_code, 403)


class ParentPortalContentTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.parent = make_user(self.school, "PARENT")
        self.learner = make_learner(self.school, grade=5, upi="UPI001")
        make_guardian(self.school, learners=[self.learner], user=self.parent)
        structure = FeeStructure.objects.create(
            school=self.school, grade=5, term=2, year=2026, amount=Decimal("8000"),
            breakdown={"Tuition": "6000", "Lunch": "2000"},
        )
        FeeStructure.objects.create(
            school=self.school, grade=5, term=3, year=2026, amount=Decimal("9000"),
        )
        Invoice.objects.create(
            school=self.school, learner=self.learner,
            fee_structure=structure, amount_due=Decimal("8000"),
        )

    def test_the_family_sees_profile_fees_and_next_term(self):
        self.client.force_authenticate(self.parent)
        res = self.client.get("/api/parent/summary/?term=2&year=2026")
        self.assertEqual(res.status_code, 200)
        (child,) = res.data["children"]
        self.assertEqual(child["profile"]["upi"], "UPI001")
        self.assertIn("date_of_birth", child["profile"])
        self.assertEqual(child["fees"]["balance"], "8000.00")
        self.assertEqual(child["fees"]["next_term"], 3)
        self.assertEqual(child["fees"]["next_term_fee"], "9000.00")
        self.assertEqual(child["fees"]["next_term_total_due"], "17000.00")
        invoice = child["fees"]["invoices"][0]
        self.assertEqual(invoice["breakdown"]["Tuition"], "6000")
        self.assertEqual(invoice["term"], 2)
