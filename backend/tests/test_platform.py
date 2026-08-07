"""The control plane: provisioning, billing, the entitlement gate, and the
operator/tenant boundary."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.common.audit import AuditEntry
from apps.platform.models import (
    Plan,
    PlatformAnnouncement,
    Subscription,
)
from apps.platform.services import (
    issue_invoice,
    mark_invoice_paid,
    provision_school,
)
from tests.factories import make_learner, make_school, make_teacher, make_user

User = get_user_model()


def make_operator(username="owner"):
    op = User.objects.create_user(username=username, password="pw", school=None)
    op.is_superuser = True
    op.save()
    return op


def make_plan(**kw):
    return Plan.objects.create(
        name=kw.get("name", "Standard"),
        price_per_learner=kw.get("price_per_learner", Decimal("50")),
        minimum_charge=kw.get("minimum_charge", Decimal("3000")),
        trial_days=kw.get("trial_days", 30),
    )


def subscribe(school, plan, **kw):
    return Subscription.objects.create(school=school, plan=plan, **kw)


class ProvisioningTests(APITestCase):
    def setUp(self):
        self.operator = make_operator()
        self.plan = make_plan()

    def test_provisioning_creates_school_admin_and_subscription(self):
        school, admin, sub, generated = provision_school(
            name="Green Valley", code="GV001", county="Nakuru", plan=self.plan,
            operator=self.operator, admin_first_name="Jane", admin_last_name="Doe",
        )
        self.assertEqual(admin.role, "ADMIN")
        self.assertEqual(admin.school_id, school.id)
        self.assertTrue(admin.must_change_password)
        self.assertTrue(admin.check_password(generated))
        self.assertEqual(sub.status, Subscription.Status.TRIAL)
        self.assertIsNotNone(sub.trial_ends_on)

    def test_provisioning_is_recorded_in_the_audit_log(self):
        provision_school(
            name="Green Valley", code="GV001", county="Nakuru", plan=self.plan,
            operator=self.operator, admin_first_name="Jane", admin_last_name="Doe",
        )
        self.assertTrue(AuditEntry.objects.filter(action="SCHOOL_PROVISIONED").exists())

    def test_the_operator_endpoint_provisions(self):
        self.client.force_authenticate(self.operator)
        res = self.client.post(
            "/api/platform/provision/",
            {
                "name": "Hilltop", "code": "HT001", "county": "Kiambu",
                "plan": self.plan.id,
                "admin_first_name": "Sam", "admin_last_name": "Kim",
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertIn("generated_password", res.data["admin"])

    def test_provisioning_stores_the_full_school_profile(self):
        """The MoE classification and location fields set at registration land
        on the school row."""
        from apps.schools.models import School

        self.client.force_authenticate(self.operator)
        res = self.client.post(
            "/api/platform/provision/",
            {
                "name": "Gikuu Primary and JSS", "code": "GK-990", "county": "Murang'a",
                "subcounty": "Kangema", "ward": "Muguru", "zone": "Central",
                "levels": ["PRIMARY", "JSS"], "kemis_code": "NEM-12345",
                "category": "SUB_COUNTY", "gender": "MIXED",
                "accommodation": "DAY", "ownership": "PUBLIC",
                "plan": self.plan.id,
                "admin_first_name": "Stephen", "admin_last_name": "Waweru",
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        school = School.objects.get(code="GK-990")
        self.assertEqual(school.county, "Murang'a")
        self.assertEqual(school.ward, "Muguru")
        self.assertEqual(school.zone, "Central")
        self.assertEqual(school.category, "SUB_COUNTY")
        self.assertEqual(school.gender, "MIXED")
        self.assertEqual(school.accommodation, "DAY")
        self.assertEqual(school.ownership, "PUBLIC")
        self.assertEqual(school.levels, ["PRIMARY", "JSS"])
        self.assertEqual(school.kemis_code, "NEM-12345")

    def test_levels_are_normalised_on_the_way_in(self):
        """The form sends checked codes; junk is dropped, duplicates removed,
        order made canonical, and a legacy 'COMPOSITE' expands to all three."""
        from apps.schools.models import School

        self.assertEqual(School.normalize_levels(["SSS", "PRIMARY", "SSS"]),
                         ["PRIMARY", "SSS"])
        self.assertEqual(School.normalize_levels(["COMPOSITE"]),
                         ["PRIMARY", "JSS", "SSS"])
        self.assertEqual(School.normalize_levels(["nonsense", "jss"]), ["JSS"])
        self.assertEqual(School.normalize_levels([]), [])

    def test_a_school_can_hold_more_than_one_level(self):
        from apps.schools.models import School

        self.client.force_authenticate(self.operator)
        res = self.client.post(
            "/api/platform/provision/",
            {
                "name": "All Through Academy", "code": "AT-1", "county": "Nairobi",
                "levels": ["SSS", "PRIMARY", "JSS"],
                "plan": self.plan.id,
                "admin_first_name": "A", "admin_last_name": "B",
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        school = School.objects.get(code="AT-1")
        self.assertEqual(school.levels, ["PRIMARY", "JSS", "SSS"])

    def test_the_optional_profile_may_be_omitted(self):
        """A bare registration still works — the extra fields all allow blank."""
        self.client.force_authenticate(self.operator)
        res = self.client.post(
            "/api/platform/provision/",
            {
                "name": "Bare Minimum", "code": "BM-1", "county": "Nairobi",
                "plan": self.plan.id,
                "admin_first_name": "A", "admin_last_name": "B",
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)

    def test_a_duplicate_school_code_is_rejected(self):
        make_school("Existing", code="DUP1")
        self.client.force_authenticate(self.operator)
        res = self.client.post(
            "/api/platform/provision/",
            {
                "name": "New", "code": "DUP1", "county": "Kiambu",
                "plan": self.plan.id,
                "admin_first_name": "A", "admin_last_name": "B",
            },
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_a_school_admin_cannot_provision(self):
        school = make_school()
        admin = make_user(school, "ADMIN")
        self.client.force_authenticate(admin)
        res = self.client.post(
            "/api/platform/provision/",
            {"name": "X", "code": "X1", "county": "Y", "plan": self.plan.id,
             "admin_first_name": "A", "admin_last_name": "B"},
            format="json",
        )
        self.assertEqual(res.status_code, 403)


class BillingTests(APITestCase):
    def setUp(self):
        self.operator = make_operator()
        self.plan = make_plan(price_per_learner=Decimal("50"), minimum_charge=Decimal("3000"))
        self.school = make_school()
        self.sub = subscribe(self.school, self.plan, status=Subscription.Status.TRIAL)

    def test_invoice_amount_is_learners_times_price(self):
        for _ in range(100):
            make_learner(self.school)
        invoice = issue_invoice(
            subscription=self.sub, period_label="Term 2 2026",
            period_end=timezone.localdate() + timedelta(days=90), operator=self.operator,
        )
        self.assertEqual(invoice.learner_count, 100)
        self.assertEqual(invoice.amount, Decimal("5000"))  # 100 * 50

    def test_a_tiny_school_pays_the_minimum(self):
        for _ in range(10):
            make_learner(self.school)
        invoice = issue_invoice(
            subscription=self.sub, period_label="Term 2 2026",
            period_end=timezone.localdate() + timedelta(days=90), operator=self.operator,
        )
        self.assertEqual(invoice.amount, Decimal("3000"))  # floor, not 500

    def test_marking_paid_extends_access_and_activates(self):
        make_learner(self.school)
        end = timezone.localdate() + timedelta(days=90)
        invoice = issue_invoice(
            subscription=self.sub, period_label="Term 2 2026",
            period_end=end, operator=self.operator,
        )
        mark_invoice_paid(invoice=invoice, operator=self.operator, reference="QGH7XZ")
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.paid_through, end)
        self.assertEqual(self.sub.status, Subscription.Status.ACTIVE)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "PAID")
        self.assertEqual(invoice.payment_reference, "QGH7XZ")

    def test_the_amount_is_snapshotted_not_recomputed(self):
        for _ in range(20):
            make_learner(self.school)
        invoice = issue_invoice(
            subscription=self.sub, period_label="Term 2 2026",
            period_end=timezone.localdate() + timedelta(days=90), operator=self.operator,
        )
        original = invoice.amount
        for _ in range(50):  # school grows after the invoice is raised
            make_learner(self.school)
        invoice.refresh_from_db()
        self.assertEqual(invoice.amount, original)

    def test_paying_is_audited(self):
        make_learner(self.school)
        invoice = issue_invoice(
            subscription=self.sub, period_label="T2", period_end=timezone.localdate(),
            operator=self.operator,
        )
        mark_invoice_paid(invoice=invoice, operator=self.operator)
        self.assertTrue(AuditEntry.objects.filter(action="SUBSCRIPTION_PAID").exists())


class EffectiveStateTests(APITestCase):
    def setUp(self):
        self.plan = make_plan()
        self.school = make_school()
        self.today = timezone.localdate()

    def _sub(self, **kw):
        return subscribe(self.school, self.plan, **kw)

    def test_a_live_trial_is_writable(self):
        sub = self._sub(status=Subscription.Status.TRIAL,
                        trial_ends_on=self.today + timedelta(days=5))
        self.assertEqual(sub.effective_state(), "TRIAL")
        self.assertTrue(sub.can_write())

    def test_an_expired_trial_never_paid_is_read_only(self):
        sub = self._sub(status=Subscription.Status.TRIAL,
                        trial_ends_on=self.today - timedelta(days=1))
        self.assertEqual(sub.effective_state(), "READ_ONLY")
        self.assertFalse(sub.can_write())

    def test_a_paid_term_is_active(self):
        sub = self._sub(status=Subscription.Status.ACTIVE,
                        paid_through=self.today + timedelta(days=30))
        self.assertEqual(sub.effective_state(), "ACTIVE")

    def test_just_past_the_term_is_grace_and_still_writable(self):
        sub = self._sub(status=Subscription.Status.ACTIVE,
                        paid_through=self.today - timedelta(days=3), grace_days=14)
        self.assertEqual(sub.effective_state(), "GRACE")
        self.assertTrue(sub.can_write())

    def test_past_grace_is_read_only(self):
        sub = self._sub(status=Subscription.Status.ACTIVE,
                        paid_through=self.today - timedelta(days=30), grace_days=14)
        self.assertEqual(sub.effective_state(), "READ_ONLY")
        self.assertFalse(sub.can_write())

    def test_cancelled_is_read_only_not_locked(self):
        sub = self._sub(status=Subscription.Status.CANCELLED)
        self.assertEqual(sub.effective_state(), "CANCELLED")
        self.assertFalse(sub.can_write())


class EntitlementGateTests(APITestCase):
    """The gate that makes a lapsed school read-only."""

    def setUp(self):
        self.plan = make_plan()
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        self.today = timezone.localdate()

    def _lapse(self):
        subscribe(
            self.school, self.plan, status=Subscription.Status.ACTIVE,
            paid_through=self.today - timedelta(days=60), grace_days=14,
        )

    def _live(self):
        subscribe(
            self.school, self.plan, status=Subscription.Status.ACTIVE,
            paid_through=self.today + timedelta(days=60),
        )

    def test_a_lapsed_school_can_still_read(self):
        self._lapse()
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get("/api/learners/").status_code, 200)

    def test_a_lapsed_school_cannot_write(self):
        self._lapse()
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            "/api/timetable/rooms/", {"name": "New Lab"}, format="json"
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn("read-only", res.data["detail"].lower())

    def test_a_live_school_can_write(self):
        self._live()
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            "/api/timetable/rooms/", {"name": "New Lab"}, format="json"
        )
        self.assertEqual(res.status_code, 201)

    def test_a_lapsed_school_can_still_change_passwords(self):
        """A security action, not a feature — never blocked."""
        self._lapse()
        self.admin.set_password("old-one-12345")
        self.admin.save()
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            "/api/me/password/",
            {"current_password": "old-one-12345", "new_password": "A-new-one-98765"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)

    def test_a_school_with_no_subscription_fails_open(self):
        """A bug must never freeze a school. No row → writes allowed."""
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            "/api/timetable/rooms/", {"name": "Lab"}, format="json"
        )
        self.assertEqual(res.status_code, 201)

    def test_the_operator_is_never_gated(self):
        self._lapse()
        operator = make_operator()
        self.client.force_authenticate(operator)
        res = self.client.get("/api/platform/overview/")
        self.assertEqual(res.status_code, 200)


class BoundaryTests(APITestCase):
    """A school admin must never reach the operator plane."""

    def setUp(self):
        self.plan = make_plan()
        self.mine = make_school("Mine")
        self.theirs = make_school("Theirs")
        self.my_admin = make_user(self.mine, "ADMIN")
        self.my_sub = subscribe(self.mine, self.plan, status=Subscription.Status.TRIAL,
                                trial_ends_on=timezone.localdate() + timedelta(days=10))
        subscribe(self.theirs, self.plan, status=Subscription.Status.TRIAL)

    def test_a_school_admin_cannot_list_all_subscriptions(self):
        self.client.force_authenticate(self.my_admin)
        self.assertEqual(self.client.get("/api/platform/subscriptions/").status_code, 403)

    def test_a_school_admin_cannot_read_the_operator_overview(self):
        self.client.force_authenticate(self.my_admin)
        self.assertEqual(self.client.get("/api/platform/overview/").status_code, 403)

    def test_a_school_admin_cannot_manage_plans(self):
        self.client.force_authenticate(self.my_admin)
        res = self.client.post(
            "/api/platform/plans/",
            {"name": "Free", "price_per_learner": "0"},
            format="json",
        )
        self.assertEqual(res.status_code, 403)

    def test_a_school_admin_sees_only_their_own_standing(self):
        self.client.force_authenticate(self.my_admin)
        res = self.client.get("/api/my-school/subscription/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["subscription"]["school_name"], "Mine")

    def test_a_teacher_cannot_see_the_subscription(self):
        teacher = make_teacher(self.mine)
        self.client.force_authenticate(teacher.user)
        self.assertEqual(self.client.get("/api/my-school/subscription/").status_code, 403)

    def test_the_operator_sees_every_school(self):
        operator = make_operator()
        self.client.force_authenticate(operator)
        res = self.client.get("/api/platform/subscriptions/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["count"], 2)

    def test_a_superuser_with_a_school_is_not_an_operator(self):
        """A superuser attached to a school is a school admin who holds the
        flag, not the platform operator. The two planes must not merge."""
        from apps.platform.access import is_operator

        hybrid = make_user(self.mine, "ADMIN", username="hybrid")
        hybrid.is_superuser = True
        hybrid.save()
        self.assertFalse(is_operator(hybrid))

        self.client.force_authenticate(hybrid)
        self.assertEqual(self.client.get("/api/platform/subscriptions/").status_code, 403)
        me = self.client.get("/api/me/")
        self.assertFalse(me.data["is_operator"])


class AnnouncementTests(APITestCase):
    def setUp(self):
        self.operator = make_operator()
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")

    def test_the_operator_posts_an_announcement(self):
        self.client.force_authenticate(self.operator)
        res = self.client.post(
            "/api/platform/announcements/",
            {"title": "New: promotions", "body": "End-of-year rollover is live.",
             "category": "FEATURE"},
            format="json",
        )
        self.assertEqual(res.status_code, 201)

    def test_a_school_admin_sees_the_feed_with_an_unread_count(self):
        PlatformAnnouncement.objects.create(
            title="Maintenance", body="Sunday 2am", category="MAINTENANCE",
            created_by=self.operator,
        )
        self.client.force_authenticate(self.admin)
        res = self.client.get("/api/platform-announcements/")
        self.assertEqual(res.data["unread"], 1)
        self.assertEqual(res.data["items"][0]["title"], "Maintenance")

    def test_marking_the_feed_seen_clears_the_count(self):
        PlatformAnnouncement.objects.create(
            title="X", body="y", created_by=self.operator
        )
        self.client.force_authenticate(self.admin)
        self.client.post("/api/platform-announcements/", {}, format="json")
        res = self.client.get("/api/platform-announcements/")
        self.assertEqual(res.data["unread"], 0)

    def test_a_school_admin_cannot_post_a_platform_announcement(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            "/api/platform/announcements/",
            {"title": "Fake", "body": "x"},
            format="json",
        )
        self.assertEqual(res.status_code, 403)


class SchoolManagementTests(APITestCase):
    """Managing a school after it is live: profile/contact edits and the admin
    account — all without the operator ever seeing tenant data."""

    def setUp(self):
        self.operator = make_operator()
        self.plan = make_plan()
        self.school, self.admin, self.sub, self.pw = provision_school(
            name="Riverside", code="RS-1", county="Nairobi", plan=self.plan,
            operator=self.operator, admin_first_name="Asha", admin_last_name="Mwangi",
            admin_phone="254700111222", admin_email="asha@riverside.ac.ke",
        )
        self.url = f"/api/platform/schools/{self.school.id}/"

    def test_detail_shows_profile_admin_and_subscription(self):
        self.client.force_authenticate(self.operator)
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(set(res.data), {"school", "admins", "subscription"})
        self.assertEqual(res.data["school"]["code"], "RS-1")
        self.assertEqual(len(res.data["admins"]), 1)
        admin = res.data["admins"][0]
        self.assertEqual(admin["phone"], "254700111222")
        self.assertEqual(admin["email"], "asha@riverside.ac.ke")

    def test_detail_never_leaks_tenant_data(self):
        """The operator must not see the school's learners through this endpoint."""
        make_learner(self.school)
        self.client.force_authenticate(self.operator)
        res = self.client.get(self.url)
        # Only the three control-plane sections, and each admin exposes exactly
        # the safe contact/status fields — no tenant payload rides along.
        self.assertEqual(set(res.data), {"school", "admins", "subscription"})
        self.assertNotIn("learners", res.data["school"])
        self.assertEqual(
            set(res.data["admins"][0]),
            {"id", "username", "name", "first_name", "last_name", "phone",
             "email", "is_active", "must_change_password", "last_login"},
        )

    def test_operator_can_edit_school_contact(self):
        self.client.force_authenticate(self.operator)
        res = self.client.patch(
            self.url,
            {"contact_phone": "254733000000", "contact_email": "office@riverside.ac.ke"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.school.refresh_from_db()
        self.assertEqual(self.school.contact_phone, "254733000000")
        self.assertEqual(self.school.contact_email, "office@riverside.ac.ke")
        self.assertTrue(AuditEntry.objects.filter(action="SCHOOL_UPDATED").exists())

    def test_resetting_the_admin_password_returns_a_handover_and_kills_the_token(self):
        from rest_framework.authtoken.models import Token

        old = Token.objects.create(user=self.admin)
        self.client.force_authenticate(self.operator)
        res = self.client.post(
            f"{self.url}admin/{self.admin.id}/reset-password/", {}, format="json"
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("generated_password", res.data)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.must_change_password)
        self.assertTrue(self.admin.check_password(res.data["generated_password"]))
        self.assertFalse(Token.objects.filter(key=old.key).exists())

    def test_changing_the_admin_retires_the_old_one(self):
        self.client.force_authenticate(self.operator)
        res = self.client.post(
            f"{self.url}admin/",
            {"first_name": "Brian", "last_name": "Otieno", "phone": "254711222333"},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertIn("generated_password", res.data)
        self.admin.refresh_from_db()
        self.assertFalse(self.admin.is_active)  # the old admin is retired
        new = User.objects.get(username=res.data["admin"]["username"])
        self.assertTrue(new.is_active)
        self.assertEqual(new.role, "ADMIN")
        self.assertEqual(new.school_id, self.school.id)
        self.assertTrue(AuditEntry.objects.filter(action="ADMIN_REPLACED").exists())

    def test_operator_can_correct_an_admins_contact(self):
        self.client.force_authenticate(self.operator)
        res = self.client.patch(
            f"{self.url}admin/{self.admin.id}/",
            {"phone": "254799888777"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.phone, "254799888777")

    def test_a_school_admin_cannot_reach_the_management_endpoint(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(
            self.client.post(f"{self.url}admin/", {}, format="json").status_code, 403
        )
