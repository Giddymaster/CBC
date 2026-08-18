"""Contact verification flips the flags; 2FA gates the token behind a code."""

from rest_framework.test import APITestCase

from apps.accounts.models import Verification
from tests.factories import make_guardian, make_learner, make_school, make_user
from tests.test_verification import _code_from_sms


class ContactVerifyTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.user = make_user(
            self.school, "TEACHER", phone="254711222333", email="t@school.ac.ke"
        )
        self.client.force_authenticate(self.user)

    def test_sms_code_verifies_the_phone(self):
        res = self.client.post("/api/me/verify/request/", {"channel": "SMS"}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertIn("****", res.data["target"])
        code = _code_from_sms("254711222333")
        done = self.client.post("/api/me/verify/confirm/", {"code": code}, format="json")
        self.assertEqual(done.status_code, 200, done.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.phone_verified)

    def test_the_email_link_verifies_the_email(self):
        self.client.post("/api/me/verify/request/", {"channel": "EMAIL"}, format="json")
        rec = Verification.objects.filter(
            user=self.user, purpose="EMAIL_VERIFY"
        ).latest("created_at")
        # The link page posts the token — no session needed.
        anon = self.client.__class__()
        done = anon.post("/api/verify/confirm-link/", {"token": rec.token}, format="json")
        self.assertEqual(done.status_code, 200, done.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_verified)

    def test_a_wrong_code_does_not_verify(self):
        self.client.post("/api/me/verify/request/", {"channel": "SMS"}, format="json")
        done = self.client.post("/api/me/verify/confirm/", {"code": "000000"}, format="json")
        self.assertEqual(done.status_code, 400)
        self.user.refresh_from_db()
        self.assertFalse(self.user.phone_verified)

    def test_a_reset_link_cannot_be_spent_as_a_contact_verification(self):
        from apps.accounts.verification import request_verification

        rec = request_verification(
            channel="EMAIL", purpose="PASSWORD_RESET",
            target="t@school.ac.ke", user=self.user,
        )
        res = self.client.post("/api/verify/confirm-link/", {"token": rec.token}, format="json")
        self.assertEqual(res.status_code, 400)


class TwoFactorToggleTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.user = make_user(self.school, "ADMIN", phone="254711000999")
        self.client.force_authenticate(self.user)

    def test_2fa_needs_a_verified_contact_first(self):
        res = self.client.post("/api/me/2fa/", {"enabled": True}, format="json")
        self.assertEqual(res.status_code, 400)
        self.user.phone_verified = True
        self.user.save(update_fields=["phone_verified"])
        res = self.client.post("/api/me/2fa/", {"enabled": True}, format="json")
        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.two_factor_enabled)


class TwoFactorLoginTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.user = make_user(
            self.school, "ADMIN", username="sec-admin", phone="254722999888"
        )
        self.user.set_password("their-password-9")
        self.user.phone_verified = True
        self.user.two_factor_enabled = True
        self.user.save()

    def _login(self, **extra):
        return self.client.post(
            "/api/auth/token/",
            {"username": "sec-admin", "password": "their-password-9", **extra},
            format="json",
        )

    def test_the_password_alone_earns_a_challenge_not_a_token(self):
        res = self._login()
        self.assertEqual(res.status_code, 200, res.data)
        self.assertTrue(res.data.get("two_factor_required"))
        self.assertNotIn("token", res.data)
        self.assertIn("****", res.data["target"])

    def test_the_code_completes_the_sign_in(self):
        self._login()  # sends the code
        code = _code_from_sms("254722999888")
        res = self._login(code=code)
        self.assertEqual(res.status_code, 200, res.data)
        self.assertIn("token", res.data)

    def test_a_wrong_code_is_refused(self):
        self._login()
        res = self._login(code="000000")
        self.assertEqual(res.status_code, 400)

    def test_a_wrong_password_never_sends_a_code(self):
        res = self.client.post(
            "/api/auth/token/",
            {"username": "sec-admin", "password": "wrong"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertFalse(
            Verification.objects.filter(user=self.user, purpose="LOGIN_2FA").exists()
        )

    def test_users_without_2fa_sign_in_as_before(self):
        plain = make_user(self.school, "TEACHER", username="plain-t")
        plain.set_password("plain-pw-999")
        plain.save()
        res = self.client.post(
            "/api/auth/token/",
            {"username": "plain-t", "password": "plain-pw-999"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("token", res.data)


class AutoVerifyOnCreationTests(APITestCase):
    def test_a_self_service_parent_gets_a_verification_started(self):
        school = make_school(code="MOE-9")
        learner = make_learner(school, admission_number="ADM900", upi="UPI900")
        make_guardian(school, learners=[learner], phone="254733111222")
        res = self.client.post(
            "/api/auth/token/",
            {"username": "ADM900", "password": "UPI900", "school_code": "MOE-9"},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertTrue(
            Verification.objects.filter(
                purpose__in=["PHONE_VERIFY", "EMAIL_VERIFY"]
            ).exists()
        )
