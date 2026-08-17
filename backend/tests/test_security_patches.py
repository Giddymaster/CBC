"""Regression tests for the security-audit patches.

Each test is one closed hole: a request that used to succeed and must now be
refused. Named for the exploit, so a future change that reopens one fails here
with a sentence explaining why it matters.
"""

from decimal import Decimal

from django.test import override_settings
from rest_framework.test import APITestCase

from apps.payments.models import FeeStructure, Invoice
from tests.factories import (
    make_guardian,
    make_learner,
    make_school,
    make_teacher,
    make_user,
)


def _link_parent(school, learner):
    parent = make_user(school, "PARENT")
    guardian = make_guardian(school, [learner])
    guardian.user = parent
    guardian.save(update_fields=["user"])
    return parent


class InvoiceWriteGuardTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.learner = make_learner(self.school, grade=7)
        self.parent = _link_parent(self.school, self.learner)
        structure = FeeStructure.objects.create(
            school=self.school, grade=7, term=1, year=2026, amount=Decimal("10000")
        )
        self.invoice = Invoice.objects.create(
            school=self.school, learner=self.learner, fee_structure=structure,
            amount_due=Decimal("10000"), amount_paid=Decimal("0"),
        )

    def test_a_parent_cannot_zero_their_own_bill(self):
        self.client.force_authenticate(self.parent)
        res = self.client.patch(
            f"/api/payments/invoices/{self.invoice.id}/",
            {"amount_due": "0"}, format="json",
        )
        self.assertIn(res.status_code, (403, 405))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amount_due, Decimal("10000"))

    def test_a_parent_cannot_delete_the_debt(self):
        self.client.force_authenticate(self.parent)
        res = self.client.delete(f"/api/payments/invoices/{self.invoice.id}/")
        self.assertIn(res.status_code, (403, 405))
        self.assertTrue(Invoice.objects.filter(pk=self.invoice.id).exists())


class ScoreWriteGuardTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.learner = make_learner(self.school, grade=7)
        self.parent = _link_parent(self.school, self.learner)

    def test_a_parent_cannot_post_a_score(self):
        from tests.factories import make_assessment, make_learning_area

        assessment = make_assessment(
            self.school, learning_area=make_learning_area("Maths", "MATH"), grade=7
        )
        self.client.force_authenticate(self.parent)
        res = self.client.post(
            "/api/scores/",
            {"assessment": assessment.id, "learner": self.learner.id, "marks": 100},
            format="json",
        )
        self.assertEqual(res.status_code, 403)


class ReportCardIdorTests(APITestCase):
    def test_a_parent_cannot_read_another_familys_report_card(self):
        school = make_school()
        mine = make_learner(school, grade=7)
        theirs = make_learner(school, grade=7)
        parent = _link_parent(school, mine)
        self.client.force_authenticate(parent)
        ok = self.client.get(f"/api/report-card/{mine.id}/")
        self.assertEqual(ok.status_code, 200)
        denied = self.client.get(f"/api/report-card/{theirs.id}/")
        self.assertEqual(denied.status_code, 403)


class LearnerEnumerationTests(APITestCase):
    def test_a_parent_lists_only_their_own_children(self):
        school = make_school()
        mine = make_learner(school, grade=7)
        make_learner(school, grade=7)  # another family's child
        parent = _link_parent(school, mine)
        self.client.force_authenticate(parent)
        res = self.client.get("/api/learners/")
        ids = [row["id"] for row in res.data["results"]]
        self.assertEqual(ids, [mine.id])


class AttendanceWriteGuardTests(APITestCase):
    def test_a_parent_cannot_mark_the_register(self):
        school = make_school()
        learner = make_learner(school, grade=7)
        parent = _link_parent(school, learner)
        self.client.force_authenticate(parent)
        res = self.client.post(
            "/api/attendance/",
            {"learner": learner.id, "date": "2026-08-17", "status": "P"},
            format="json",
        )
        self.assertEqual(res.status_code, 403)


class PeerReviewTenancyTests(APITestCase):
    def test_a_teacher_cannot_read_another_schools_peer_reviews(self):
        from apps.teachers.models import SchemeOfWork
        from apps.teachers.development import PeerReview
        from tests.factories import make_learning_area

        school_a = make_school("A")
        school_b = make_school("B")
        area = make_learning_area("Maths", "MATH")
        teacher_b = make_teacher(school_b)
        reviewer_b = make_teacher(school_b)
        scheme_b = SchemeOfWork.objects.create(
            school=school_b, teacher=teacher_b, learning_area=area,
            grade=7, term=1, year=2026,
        )
        PeerReview.objects.create(
            school=school_b, scheme=scheme_b, reviewer=reviewer_b.user,
            verdict="STRONG", comment="secret",
        )
        outsider = make_teacher(school_a)
        self.client.force_authenticate(outsider.user)
        res = self.client.get("/api/peer-reviews/")
        self.assertEqual(res.data["count"], 0)


class MustChangePasswordTests(APITestCase):
    def test_a_handover_password_reaches_nothing_but_its_own_change(self):
        school = make_school()
        admin = make_user(school, "ADMIN")
        admin.must_change_password = True
        admin.save(update_fields=["must_change_password"])
        self.client.force_authenticate(admin)
        # /me is allowed…
        self.assertEqual(self.client.get("/api/me/").status_code, 200)
        # …everything else is refused until the password is changed.
        self.assertEqual(self.client.get("/api/learners/").status_code, 403)


class WebhookAuthTests(APITestCase):
    @override_settings(DARAJA_WEBHOOK_SECRET="s3cret")
    def test_c2b_without_the_secret_credits_nothing(self):
        make_school(code="55555555")
        res = self.client.post(
            "/api/payments/c2b-confirmation/wrong/",
            {"BusinessShortCode": "55555555", "TransID": "X1",
             "TransAmount": "9999", "BillRefNumber": "ADM001"},
            format="json",
        )
        self.assertEqual(res.status_code, 403)

    @override_settings(DARAJA_WEBHOOK_SECRET="")
    def test_an_unconfigured_webhook_is_closed(self):
        res = self.client.post(
            "/api/payments/c2b-confirmation/anything/",
            {"BusinessShortCode": "55555555", "TransID": "X1", "TransAmount": "9999"},
            format="json",
        )
        self.assertEqual(res.status_code, 403)


class SignedMediaTests(APITestCase):
    def test_an_unsigned_media_request_is_refused(self):
        res = self.client.get("/media/learner_photos/whatever.jpg")
        self.assertEqual(res.status_code, 403)

    def test_a_tampered_token_is_refused(self):
        from apps.common.media import media_token

        token = media_token("learner_photos/a.jpg")
        res = self.client.get(f"/media/learner_photos/b.jpg?t={token}")
        self.assertEqual(res.status_code, 403)


class SuperuserWithSchoolTests(APITestCase):
    def test_a_superuser_with_a_school_does_not_read_other_tenants(self):
        school_a = make_school("A")
        school_b = make_school("B")
        make_learner(school_b, grade=7)
        admin_a = make_user(school_a, "ADMIN")
        admin_a.is_superuser = True
        admin_a.save(update_fields=["is_superuser"])
        self.client.force_authenticate(admin_a)
        res = self.client.get("/api/learners/")
        self.assertEqual(res.data["count"], 0)  # none of school B's learners
