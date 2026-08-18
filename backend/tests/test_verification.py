"""One-time codes and links: the engine, and password reset built on it."""

from datetime import timedelta

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import Verification
from apps.accounts.verification import (
    VerifyResult,
    confirm_code,
    consume_token,
    request_verification,
)
from tests.factories import make_school, make_user


def _code_from_sms(target):
    """Pull the six digits out of the code SMS the sender logged for a number."""
    import re

    from apps.communication.models import SmsMessage

    msg = SmsMessage.objects.filter(recipient=target).order_by("-created_at").first()
    match = re.search(r"\b(\d{6})\b", msg.body) if msg else None
    if not match:
        raise AssertionError("no code SMS found")
    return match.group(1)


class VerificationEngineTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.user = make_user(self.school, "PARENT", username="mama", email="mama@x.com")

    def _last_code(self, record):
        # The plaintext is never stored, but it rides out in the SMS body, so
        # tests read it from the message the sender logged.
        return _code_from_sms(record.target)

    def test_an_sms_request_sends_a_code_and_confirms(self):
        rec = request_verification(
            channel="SMS", purpose="PASSWORD_RESET", target="254700000001",
            user=self.user, school=self.school,
        )
        code = self._last_code(rec)
        self.assertEqual(confirm_code(rec, code), VerifyResult.OK)
        rec.refresh_from_db()
        self.assertIsNotNone(rec.consumed_at)

    def test_a_used_code_cannot_be_replayed(self):
        rec = request_verification(channel="SMS", purpose="LOGIN_2FA", target="254700000001")
        code = self._last_code(rec)
        confirm_code(rec, code)
        self.assertEqual(confirm_code(rec, code), VerifyResult.NOT_FOUND)

    def test_a_wrong_code_is_rejected_and_counts_against_the_cap(self):
        rec = request_verification(channel="SMS", purpose="LOGIN_2FA", target="254700000001")
        self.assertEqual(confirm_code(rec, "000000"), VerifyResult.BAD_CODE)
        rec.refresh_from_db()
        self.assertEqual(rec.attempts, 1)

    @override_settings(OTP_MAX_ATTEMPTS=3)
    def test_guessing_runs_out(self):
        rec = request_verification(channel="SMS", purpose="LOGIN_2FA", target="254700000001")
        for _ in range(3):
            confirm_code(rec, "111111")
        self.assertEqual(confirm_code(rec, "111111"), VerifyResult.TOO_MANY)

    def test_an_expired_code_is_rejected(self):
        rec = request_verification(channel="SMS", purpose="LOGIN_2FA", target="254700000001")
        rec.expires_at = timezone.now() - timedelta(minutes=1)
        rec.save(update_fields=["expires_at"])
        self.assertEqual(confirm_code(rec, self._last_code(rec)), VerifyResult.EXPIRED)

    def test_an_email_request_mints_a_link_token(self):
        rec = request_verification(
            channel="EMAIL", purpose="PASSWORD_RESET", target="mama@x.com", user=self.user,
        )
        self.assertTrue(rec.token)
        got = consume_token(rec.token, purpose="PASSWORD_RESET")
        self.assertEqual(got.id, rec.id)
        # Burned: a second use fails.
        self.assertIsNone(consume_token(rec.token, purpose="PASSWORD_RESET"))

    def test_the_code_is_only_stored_hashed(self):
        rec = request_verification(channel="SMS", purpose="LOGIN_2FA", target="254700000001")
        self.assertNotIn(self._last_code(rec), rec.code_hash)


class PasswordResetTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.user = make_user(self.school, "ADMIN", username="office",
                              email="office@school.ac.ke", phone="254700111222")
        self.user.set_password("old-password")
        self.user.save()

    def _live(self, target):
        return Verification.objects.filter(
            target=target, purpose="PASSWORD_RESET", consumed_at__isnull=True
        ).order_by("-created_at").first()

    def _code(self, rec):
        return _code_from_sms(rec.target)

    def test_reset_by_email_link(self):
        req = self.client.post("/api/password-reset/request/",
                               {"identifier": "office@school.ac.ke"}, format="json")
        self.assertEqual(req.status_code, 200)
        self.assertEqual(req.data["channel"], "EMAIL")
        rec = self._live("office@school.ac.ke")
        done = self.client.post("/api/password-reset/confirm/",
                                {"token": rec.token, "new_password": "brand-new-pw-9"},
                                format="json")
        self.assertEqual(done.status_code, 200, done.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("brand-new-pw-9"))

    def test_reset_by_sms_code(self):
        self.client.post("/api/password-reset/request/",
                         {"identifier": "0700111222"}, format="json")
        rec = self._live("254700111222")
        self.assertIsNotNone(rec)
        done = self.client.post(
            "/api/password-reset/confirm/",
            {"identifier": "0700111222", "code": self._code(rec),
             "new_password": "texted-new-pw-9"},
            format="json",
        )
        self.assertEqual(done.status_code, 200, done.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("texted-new-pw-9"))

    def test_an_unknown_identifier_looks_identical_and_sets_nothing(self):
        res = self.client.post("/api/password-reset/request/",
                               {"identifier": "nobody@nowhere.com"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["channel"], "EMAIL")
        self.assertFalse(Verification.objects.exists())

    def test_a_wrong_code_does_not_reset(self):
        self.client.post("/api/password-reset/request/",
                         {"identifier": "0700111222"}, format="json")
        res = self.client.post(
            "/api/password-reset/confirm/",
            {"identifier": "0700111222", "code": "000000", "new_password": "x-9-longenough"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("old-password"))

    def test_the_link_is_single_use(self):
        self.client.post("/api/password-reset/request/",
                         {"identifier": "office@school.ac.ke"}, format="json")
        rec = self._live("office@school.ac.ke")
        first = self.client.post("/api/password-reset/confirm/",
                                 {"token": rec.token, "new_password": "first-pw-99"},
                                 format="json")
        self.assertEqual(first.status_code, 200)
        again = self.client.post("/api/password-reset/confirm/",
                                 {"token": rec.token, "new_password": "second-pw-99"},
                                 format="json")
        self.assertEqual(again.status_code, 400)

    def test_peek_tells_the_link_page_what_it_is_without_spending_it(self):
        self.client.post("/api/password-reset/request/",
                         {"identifier": "office@school.ac.ke"}, format="json")
        rec = self._live("office@school.ac.ke")
        res = self.client.get(f"/api/verify/{rec.token}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["purpose"], "PASSWORD_RESET")
        self.assertIn("@", res.data["target"])
        self.assertNotEqual(res.data["target"], "office@school.ac.ke")  # masked
        # Still usable — the peek did not consume it.
        self.assertIsNotNone(self._live("office@school.ac.ke"))
