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
            self.school, grade=5, admission_number="ADM0126", upi="UPI777",
        )
        self.guardian = make_guardian(self.school, learners=[self.learner])

    def test_the_office_issues_a_login_admission_number_as_username_upi_as_password(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            "/api/parent-logins/", {"learner": self.learner.id}, format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["username"], "adm0126")
        # Admission number is the username, the UPI is the first password —
        # two things the parent already has on the report form.
        self.assertEqual(res.data["generated_password"], "UPI777")
        self.guardian.refresh_from_db()
        self.assertIsNotNone(self.guardian.user)
        self.assertEqual(self.guardian.user.role, "PARENT")
        self.assertTrue(self.guardian.user.must_change_password)

        # Login with school code + admission number + UPI works straight away.
        self.client.force_authenticate(None)
        signin = self.client.post(
            "/api/auth/token/",
            {"username": "ADM0126", "password": "UPI777", "school_code": self.school.code},
            format="json",
        )
        self.assertEqual(signin.status_code, 200, signin.data)

    def test_without_a_upi_the_admission_number_stands_in_for_the_password(self):
        no_upi = make_learner(self.school, grade=5, admission_number="ADM0200", upi="")
        make_guardian(self.school, learners=[no_upi])
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            "/api/parent-logins/", {"learner": no_upi.id}, format="json",
        )
        self.assertEqual(res.data["generated_password"], "ADM0200")

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


class SchoolCodeScopingTests(APITestCase):
    """The school code is what tells the platform which tenant a login is for
    once many schools share admission numbers."""

    def setUp(self):
        # Two schools, both using "ADM001" — the whole point.
        self.school_a = make_school("Alpha", code="SCH-A")
        self.school_b = make_school("Beta", code="SCH-B")
        self.learner_a = make_learner(
            self.school_a, admission_number="ADM001", upi="UPI-A")
        self.learner_b = make_learner(
            self.school_b, admission_number="ADM001", upi="UPI-B")
        self._issue(self.school_a, self.learner_a)
        self._issue(self.school_b, self.learner_b)

    def _issue(self, school, learner):
        make_guardian(school, learners=[learner])
        admin = make_user(school, "ADMIN")
        self.client.force_authenticate(admin)
        self.client.post("/api/parent-logins/", {"learner": learner.id}, format="json")
        self.client.force_authenticate(None)

    def test_the_code_routes_the_same_admission_number_to_the_right_school(self):
        a = self.client.post(
            "/api/auth/token/",
            {"username": "ADM001", "password": "UPI-A", "school_code": "SCH-A"},
            format="json",
        )
        self.assertEqual(a.status_code, 200, a.data)
        # School A's parent is signed in — not School B's, though both are ADM001.
        self.assertEqual(a.data["role"], "PARENT")

        b = self.client.post(
            "/api/auth/token/",
            {"username": "ADM001", "password": "UPI-B", "school_code": "SCH-B"},
            format="json",
        )
        self.assertEqual(b.status_code, 200, b.data)
        self.assertNotEqual(a.data["username"], b.data["username"])

    def test_the_right_password_on_the_wrong_code_is_refused(self):
        # School A's UPI, but claiming School B — must fail, not cross tenants.
        res = self.client.post(
            "/api/auth/token/",
            {"username": "ADM001", "password": "UPI-A", "school_code": "SCH-B"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_wrong_code_and_wrong_password_read_identically(self):
        """No oracle: a distinct "wrong school code" answer would only appear
        after the password verified, letting an attacker confirm stolen
        passwords by reading which error came back."""
        wrong_code = self.client.post(
            "/api/auth/token/",
            {"username": "ADM001", "password": "UPI-A", "school_code": "SCH-B"},
            format="json",
        )
        wrong_password = self.client.post(
            "/api/auth/token/",
            {"username": "ADM001", "password": "NOT-IT", "school_code": "SCH-B"},
            format="json",
        )
        self.assertEqual(wrong_code.status_code, wrong_password.status_code)
        self.assertEqual(wrong_code.data, wrong_password.data)

    def test_an_unknown_school_code_signs_no_one_in(self):
        res = self.client.post(
            "/api/auth/token/",
            {"username": "ADM001", "password": "UPI-A", "school_code": "NOPE"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)


class SelfServiceParentTests(APITestCase):
    """A parent signs in straight from the report form — school code, admission
    number and UPI — with no login created by the office first."""

    def setUp(self):
        self.school = make_school("Alpha", code="MOE-1")
        self.learner = make_learner(
            self.school, admission_number="ADM0649", upi="UPI607113")
        self.guardian = make_guardian(self.school, learners=[self.learner])

    def _login(self, code="MOE-1", adm="ADM0649", upi="UPI607113"):
        return self.client.post(
            "/api/auth/token/",
            {"username": adm, "password": upi, "school_code": code},
            format="json",
        )

    def test_first_login_creates_the_account_from_the_report_form(self):
        from apps.accounts.models import User

        self.assertFalse(User.objects.filter(role="PARENT").exists())
        res = self._login()
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["role"], "PARENT")
        self.assertTrue(res.data["must_change_password"])
        self.guardian.refresh_from_db()
        self.assertIsNotNone(self.guardian.user)

    def test_the_second_login_uses_the_same_account(self):
        from apps.accounts.models import User

        self._login()
        self._login()
        self.assertEqual(User.objects.filter(role="PARENT").count(), 1)

    def test_a_wrong_upi_creates_nothing_and_is_refused(self):
        from apps.accounts.models import User

        res = self._login(upi="WRONG")
        self.assertEqual(res.status_code, 400)
        self.assertFalse(User.objects.filter(role="PARENT").exists())

    def test_the_wrong_school_code_matches_no_learner(self):
        other = make_school("Beta", code="MOE-2")
        make_learner(other, admission_number="ADM0649", upi="DIFFERENT")
        res = self._login(code="MOE-2")  # ADM0649 exists there but UPI differs
        self.assertEqual(res.status_code, 400)

    def test_after_the_parent_sets_a_password_the_upi_no_longer_works(self):
        self._login()  # provisions, must_change_password
        self.guardian.refresh_from_db()
        user = self.guardian.user
        user.set_password("my-own-password")
        user.must_change_password = False
        user.save()
        # The UPI must not reopen the account once a real password is chosen.
        res = self._login()
        self.assertEqual(res.status_code, 400)


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
