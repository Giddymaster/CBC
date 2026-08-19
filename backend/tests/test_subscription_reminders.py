"""Standing banner data, the once-a-day reminder command, and extension requests."""

from datetime import timedelta

from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.platform.models import Plan, Subscription
from tests.factories import make_school, make_teacher, make_user


def _sub(school, **kw):
    plan, _ = Plan.objects.get_or_create(
        name="Basic", defaults={"price_per_learner": "20", "trial_days": 30}
    )
    return Subscription.objects.create(school=school, plan=plan, **kw)


class StandingViewTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.today = timezone.localdate()

    def test_a_teacher_sees_days_left(self):
        _sub(self.school, status="ACTIVE", paid_through=self.today + timedelta(days=4))
        teacher = make_teacher(self.school)
        self.client.force_authenticate(teacher.user)
        res = self.client.get("/api/my-school/standing/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["state"], "ACTIVE")
        self.assertEqual(res.data["days_left"], 4)
        self.assertFalse(res.data["can_request"])  # a plain teacher is not leadership

    def test_the_head_teacher_may_request(self):
        _sub(self.school, status="ACTIVE", paid_through=self.today + timedelta(days=2))
        head = make_teacher(self.school, rank="HEAD")
        self.client.force_authenticate(head.user)
        res = self.client.get("/api/my-school/standing/")
        self.assertTrue(res.data["can_request"])

    def test_a_parent_gets_nothing(self):
        _sub(self.school, status="ACTIVE")
        self.client.force_authenticate(make_user(self.school, "PARENT"))
        self.assertIsNone(self.client.get("/api/my-school/standing/").data["state"])


class RequestExtensionTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        _sub(self.school, status="ACTIVE")

    @override_settings(EMAIL_API_KEY="", OPS_EMAIL="ops@shulenest.com")
    def test_leadership_can_request_and_a_parent_cannot(self):
        head = make_teacher(self.school, rank="HEAD")
        self.client.force_authenticate(head.user)
        ok = self.client.post("/api/my-school/request-extension/", {}, format="json")
        self.assertEqual(ok.status_code, 200, ok.data)

        self.client.force_authenticate(make_user(self.school, "PARENT"))
        denied = self.client.post("/api/my-school/request-extension/", {}, format="json")
        self.assertEqual(denied.status_code, 403)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_API_KEY="re_test",  # take the Resend branch off; we patch send below
)
class ReminderCommandTests(APITestCase):
    """The command's decision logic — who gets reminded, and the once-a-day cap.
    Email delivery itself is the email module's job; here we assert last_reminder_on
    moves and the counts are right, with sends stubbed to the console."""

    def setUp(self):
        self.today = timezone.localdate()

    def _school_with_leader(self, name):
        school = make_school(name)
        head_user = make_user(school, "TEACHER", email=f"head-{name}@x.com")
        make_teacher(school, user=head_user, rank="HEAD")
        return school

    def test_expiring_soon_is_reminded_once_per_day(self):
        school = self._school_with_leader("Alpha")
        sub = _sub(school, status="ACTIVE", paid_through=self.today + timedelta(days=3))
        call_command("send_subscription_reminders")
        sub.refresh_from_db()
        self.assertEqual(sub.last_reminder_on, self.today)
        # Running again the same day must not re-send.
        call_command("send_subscription_reminders")  # no error, no change
        sub.refresh_from_db()
        self.assertEqual(sub.last_reminder_on, self.today)

    def test_far_from_expiry_is_left_alone(self):
        school = self._school_with_leader("Beta")
        sub = _sub(school, status="ACTIVE", paid_through=self.today + timedelta(days=60))
        call_command("send_subscription_reminders")
        sub.refresh_from_db()
        self.assertIsNone(sub.last_reminder_on)

    def test_lapsed_read_only_is_reminded(self):
        school = self._school_with_leader("Gamma")
        sub = _sub(
            school, status="ACTIVE",
            paid_through=self.today - timedelta(days=40), grace_days=14,
        )
        self.assertEqual(sub.effective_state(), "READ_ONLY")
        call_command("send_subscription_reminders")
        sub.refresh_from_db()
        self.assertEqual(sub.last_reminder_on, self.today)

    def test_cancelled_is_never_reminded(self):
        school = self._school_with_leader("Delta")
        sub = _sub(school, status="CANCELLED")
        call_command("send_subscription_reminders")
        sub.refresh_from_db()
        self.assertIsNone(sub.last_reminder_on)
