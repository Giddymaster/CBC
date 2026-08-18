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


class MyContactTests(APITestCase):
    """Adding your own email/phone — what makes reset and 2FA reachable."""

    def setUp(self):
        self.school = make_school()
        self.user = make_user(self.school, "PARENT")
        self.user.email = ""
        self.user.phone = ""
        self.user.save()
        self.client.force_authenticate(self.user)

    def test_adding_an_email_saves_it_and_starts_verification(self):
        res = self.client.post(
            "/api/me/contact/", {"email": "mama@gmail.com"}, format="json"
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["channel"], "EMAIL")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "mama@gmail.com")
        self.assertFalse(self.user.email_verified)
        self.assertTrue(
            Verification.objects.filter(user=self.user, purpose="EMAIL_VERIFY").exists()
        )

    def test_a_phone_is_normalised_and_verification_texted(self):
        res = self.client.post("/api/me/contact/", {"phone": "0722 000 111"}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone, "254722000111")
        code = _code_from_sms("254722000111")
        done = self.client.post("/api/me/verify/confirm/", {"code": code}, format="json")
        self.assertEqual(done.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.phone_verified)

    def test_changing_a_verified_email_clears_the_flag(self):
        self.user.email = "old@x.com"
        self.user.email_verified = True
        self.user.save()
        self.client.post("/api/me/contact/", {"email": "new@x.com"}, format="json")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "new@x.com")
        self.assertFalse(self.user.email_verified)

    def test_junk_is_rejected(self):
        self.assertEqual(
            self.client.post("/api/me/contact/", {"email": "not-an-email"}, format="json").status_code,
            400,
        )
        self.assertEqual(
            self.client.post("/api/me/contact/", {"phone": "123"}, format="json").status_code,
            400,
        )

    def test_reset_reaches_the_newly_added_email(self):
        """The reported bug end to end: no email on file → add one → a reset
        actually goes out to it."""
        self.client.post("/api/me/contact/", {"email": "mama@gmail.com"}, format="json")
        self.client.logout()
        self.client.force_authenticate(None)
        self.client.post(
            "/api/password-reset/request/", {"identifier": "mama@gmail.com"}, format="json"
        )
        self.assertTrue(
            Verification.objects.filter(
                user=self.user, purpose="PASSWORD_RESET", target="mama@gmail.com"
            ).exists()
        )


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
