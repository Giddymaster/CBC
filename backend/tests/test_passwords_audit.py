"""Password management and the audit trail."""

from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.common.audit import AuditEntry
from apps.students.models import Learner
from tests.factories import (
    make_learner,
    make_school,
    make_support,
    make_teacher,
    make_user,
)


class ChangeOwnPasswordTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.teacher = make_teacher(self.school)
        self.user = self.teacher.user
        self.user.set_password("oldpass12345")
        self.user.save()
        self.client.force_authenticate(self.user)

    def _change(self, current="oldpass12345", new="Str0ng-New-Pass!"):
        return self.client.post(
            "/api/me/password/",
            {"current_password": current, "new_password": new},
            format="json",
        )

    def test_a_staff_member_can_rotate_their_own_password(self):
        res = self._change()
        self.assertEqual(res.status_code, 200, res.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Str0ng-New-Pass!"))

    def test_the_current_password_is_required(self):
        res = self._change(current="not-it")
        self.assertEqual(res.status_code, 400)
        self.assertIn("current_password", res.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("oldpass12345"))

    def test_the_new_password_must_differ(self):
        res = self._change(new="oldpass12345")
        self.assertEqual(res.status_code, 400)

    def test_a_weak_password_is_refused(self):
        res = self._change(new="1234")
        self.assertEqual(res.status_code, 400)
        self.assertIn("new_password", res.data)

    def test_changing_invalidates_the_old_token(self):
        """A password change is usually a response to it being known by someone
        else. Leaving old tokens alive would make the change cosmetic."""
        old = Token.objects.create(user=self.user).key
        res = self._change()
        self.assertFalse(Token.objects.filter(key=old).exists())
        self.assertNotEqual(res.data["token"], old)

    def test_a_fresh_token_is_returned_so_the_caller_stays_signed_in(self):
        res = self._change()
        self.assertTrue(Token.objects.filter(key=res.data["token"], user=self.user).exists())

    def test_changing_clears_the_forced_flag(self):
        self.user.must_change_password = True
        self.user.save()
        self._change()
        self.user.refresh_from_db()
        self.assertFalse(self.user.must_change_password)
        self.assertIsNotNone(self.user.password_changed_at)

    def test_an_anonymous_caller_cannot(self):
        self.client.force_authenticate(None)
        self.assertEqual(self._change().status_code, 401)


class AdminResetTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        self.teacher = make_teacher(self.school)
        self.client.force_authenticate(self.admin)

    def _reset(self, user=None, **body):
        target = user or self.teacher.user
        return self.client.post(
            f"/api/school/staff/{target.id}/reset-password/", body, format="json"
        )

    def test_the_admin_gets_a_new_password_once(self):
        res = self._reset()
        self.assertEqual(res.status_code, 200, res.data)
        generated = res.data["generated_password"]
        self.teacher.user.refresh_from_db()
        self.assertTrue(self.teacher.user.check_password(generated))

    def test_the_holder_must_then_choose_their_own(self):
        """This is what stops the admin's copy remaining a working credential."""
        self._reset()
        self.teacher.user.refresh_from_db()
        self.assertTrue(self.teacher.user.must_change_password)

    def test_reset_kills_the_holders_existing_token(self):
        token = Token.objects.create(user=self.teacher.user).key
        self._reset()
        self.assertFalse(Token.objects.filter(key=token).exists())

    def test_an_admin_may_supply_a_password(self):
        res = self._reset(password="Handover-Pass-99")
        self.assertEqual(res.data["generated_password"], "Handover-Pass-99")

    def test_a_weak_supplied_password_is_refused(self):
        res = self._reset(password="abc")
        self.assertEqual(res.status_code, 400)

    def test_a_teacher_cannot_reset_anyones_password(self):
        other = make_teacher(self.school)
        self.client.force_authenticate(self.teacher.user)
        self.assertEqual(self._reset(other.user).status_code, 403)

    def test_an_admin_cannot_reach_another_schools_staff(self):
        outsider = make_teacher(make_school("Elsewhere"))
        self.assertEqual(self._reset(outsider.user).status_code, 403)

    def test_a_school_admin_cannot_reset_a_platform_superuser(self):
        root = make_user(self.school, "ADMIN", username="root")
        root.is_superuser = True
        root.save()
        self.assertEqual(self._reset(root).status_code, 403)

    def test_a_reset_is_recorded_in_the_audit_log(self):
        self._reset()
        entry = AuditEntry.objects.get(action="PASSWORD_RESET")
        self.assertEqual(entry.actor_id, self.admin.id)
        self.assertIn(self.teacher.user.get_full_name(), entry.label)

    def test_a_generated_staff_password_forces_a_change(self):
        res = self.client.post(
            "/api/school/staff/add-teacher/",
            {
                "first_name": "New", "last_name": "Teacher",
                "tsc_number": "TSC777777", "employment_type": "TSC",
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        from django.contrib.auth import get_user_model

        account = get_user_model().objects.get(username=res.data["username"])
        self.assertTrue(account.must_change_password)

    def test_an_admin_chosen_password_does_not_force_a_change(self):
        """If the admin set it deliberately with the teacher present, it is
        already theirs."""
        res = self.client.post(
            "/api/school/staff/add-teacher/",
            {
                "first_name": "Chosen", "last_name": "Teacher",
                "tsc_number": "TSC888888", "employment_type": "TSC",
                "password": "TheyPickedThis99",
            },
            format="json",
        )
        from django.contrib.auth import get_user_model

        account = get_user_model().objects.get(username=res.data["username"])
        self.assertFalse(account.must_change_password)

    def test_me_tells_the_client_to_force_a_change(self):
        self._reset()
        # force_authenticate uses the object handed to it, so it has to be the
        # one the reset actually wrote.
        self.teacher.user.refresh_from_db()
        self.client.force_authenticate(self.teacher.user)
        res = self.client.get("/api/me/")
        self.assertTrue(res.data["must_change_password"])


class AuditTrailTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        self.teacher = make_teacher(self.school)
        self.client.force_authenticate(self.admin)

    def test_deactivating_a_learner_is_recorded(self):
        learner = make_learner(self.school)
        self.client.delete(f"/api/learners/{learner.id}/")
        entry = AuditEntry.objects.get(action="LEARNER_DEACTIVATED")
        self.assertEqual(entry.actor_id, self.admin.id)
        self.assertIn(learner.admission_number, entry.label)

    def test_reactivating_is_recorded_separately(self):
        learner = make_learner(self.school, active=False)
        self.client.patch(f"/api/learners/{learner.id}/", {"active": True}, format="json")
        self.assertTrue(AuditEntry.objects.filter(action="LEARNER_REACTIVATED").exists())

    def test_an_unrelated_edit_is_not_logged(self):
        """Only decisions worth asking about later. Every incidental save would
        bury them."""
        learner = make_learner(self.school)
        self.client.patch(
            f"/api/learners/{learner.id}/", {"stream": "South"}, format="json"
        )
        self.assertEqual(AuditEntry.objects.count(), 0)

    def test_a_corrected_mark_records_both_values(self):
        from tests.factories import make_assessment

        assessment = make_assessment(self.school, grade=5)
        learner = make_learner(self.school, grade=5)
        payload = {"assessment": assessment.id, "records": [{"learner": learner.id, "marks": 34}]}
        self.client.post("/api/scores/bulk/", payload, format="json")
        self.assertEqual(AuditEntry.objects.filter(action="SCORE_CHANGED").count(), 0)

        payload["records"][0]["marks"] = 74
        self.client.post("/api/scores/bulk/", payload, format="json")
        entry = AuditEntry.objects.get(action="SCORE_CHANGED")
        self.assertEqual(entry.detail["from"], 34.0)
        self.assertEqual(entry.detail["to"], 74.0)
        self.assertEqual(entry.detail["from_level"], "BE")
        self.assertEqual(entry.detail["to_level"], "ME")

    def test_an_admission_is_recorded(self):
        self.client.post(
            "/api/admissions/",
            {
                "first_name": "Wanjiru", "last_name": "Kamau",
                "date_of_birth": "2019-04-12", "gender": "F", "grade": 1,
            },
            format="json",
        )
        self.assertTrue(AuditEntry.objects.filter(action="LEARNER_ADMITTED").exists())

    def test_granting_admission_rights_is_recorded(self):
        self.client.post(
            "/api/admission-rights/",
            {"user": self.teacher.user_id, "note": "Grade 1 intake"},
            format="json",
        )
        entry = AuditEntry.objects.get(action="RIGHTS_GRANTED")
        self.assertEqual(entry.detail["note"], "Grade 1 intake")

    def test_a_promotion_is_recorded_and_so_is_its_reversal(self):
        from apps.promotions.services import apply_run, build_run, revert_run
        from apps.schools import moe
        from apps.students.models import Pathway

        for p in moe.PATHWAYS:
            Pathway.objects.get_or_create(code=p["code"])
        make_learner(self.school, grade=5)
        run = build_run(school=self.school, from_year=2026, to_year=2027)
        apply_run(run, user=self.admin)
        revert_run(run, user=self.admin)
        self.assertTrue(AuditEntry.objects.filter(action="PROMOTION_APPLIED").exists())
        self.assertTrue(AuditEntry.objects.filter(action="PROMOTION_REVERSED").exists())

    def test_a_payment_is_recorded_even_though_a_webhook_has_no_user(self):
        from decimal import Decimal

        from apps.payments.models import FeeStructure, Invoice
        from apps.payments.services.reconcile import record_transaction

        learner = make_learner(self.school, admission_number="ADM777")
        fee = FeeStructure.objects.create(
            school=self.school, grade=5, term=1, year=2026, amount=Decimal("1000")
        )
        Invoice.objects.create(
            school=self.school, learner=learner, fee_structure=fee,
            amount_due=Decimal("1000"),
        )
        record_transaction(
            school=self.school, source="C2B", receipt="RCPT1",
            phone="254700000001", amount=Decimal("500"), account_reference="ADM777",
        )
        entry = AuditEntry.objects.get(action="PAYMENT_RECORDED")
        self.assertIsNone(entry.actor_id)
        self.assertEqual(entry.actor_name, "system")
        self.assertTrue(entry.detail["matched"])

    def test_deactivating_support_staff_is_recorded(self):
        cook = make_support(self.school)
        self.client.delete(f"/api/support-staff/{cook.id}/")
        self.assertTrue(AuditEntry.objects.filter(action="STAFF_DEACTIVATED").exists())

    def test_the_log_is_readable_by_the_admin(self):
        make_learner(self.school)
        self.client.delete(f"/api/learners/{Learner.objects.first().id}/")
        res = self.client.get("/api/audit/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["count"], 1)
        self.assertIn("action_label", res.data["results"][0])

    def test_a_teacher_cannot_read_the_log(self):
        self.client.force_authenticate(self.teacher.user)
        self.assertEqual(self.client.get("/api/audit/").status_code, 403)

    def test_the_log_is_scoped_to_the_school(self):
        elsewhere = make_school("Elsewhere")
        other_admin = make_user(elsewhere, "ADMIN")
        learner = make_learner(elsewhere)
        self.client.force_authenticate(other_admin)
        self.client.delete(f"/api/learners/{learner.id}/")

        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get("/api/audit/").data["count"], 0)

    def test_the_log_cannot_be_written_through_the_api(self):
        """A log an admin can edit is not evidence of anything."""
        res = self.client.post(
            "/api/audit/", {"action": "SCORE_CHANGED", "label": "made up"}, format="json"
        )
        self.assertIn(res.status_code, (403, 405))

    def test_the_log_cannot_be_deleted_through_the_api(self):
        make_learner(self.school)
        self.client.delete(f"/api/learners/{Learner.objects.first().id}/")
        entry = AuditEntry.objects.first()
        res = self.client.delete(f"/api/audit/{entry.id}/")
        self.assertIn(res.status_code, (403, 405))
        self.assertTrue(AuditEntry.objects.filter(pk=entry.pk).exists())

    def test_a_broken_audit_write_never_breaks_the_action(self):
        """A school that cannot save a mark because logging failed is worse off
        than one with a gap in its log."""
        from unittest.mock import patch

        from apps.common.audit import record

        with patch.object(AuditEntry.objects, "create", side_effect=RuntimeError("db down")):
            self.assertIsNone(
                record(actor=self.admin, school=self.school, action="SCORE_CHANGED")
            )

    def test_the_summary_counts_by_action(self):
        learner = make_learner(self.school)
        self.client.delete(f"/api/learners/{learner.id}/")
        res = self.client.get("/api/audit/summary/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["total"], 1)
        self.assertEqual(res.data["actions"][0]["action"], "LEARNER_DEACTIVATED")
