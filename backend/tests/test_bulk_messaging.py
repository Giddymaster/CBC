"""Bulk messages to parents: who they reach, what they say, who may send them.

Every message is charged and cannot be recalled, so these tests care most about
the count being right before the send and the words being right for the family
that reads them.
"""

from decimal import Decimal

from rest_framework.test import APITestCase

from apps.communication.models import MessageBlast, SmsMessage
from apps.payments.models import FeeStructure, Invoice
from tests.factories import (
    make_guardian,
    make_learner,
    make_school,
    make_support,
    make_teacher,
    make_user,
)


class AudienceTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        self.g5 = make_learner(self.school, grade=5, stream="North")
        self.g7 = make_learner(self.school, grade=7, stream="South")
        self.parent_a = make_guardian(self.school, [self.g5], phone="0722000111")
        self.parent_b = make_guardian(self.school, [self.g7], phone="0733000222")
        self.client.force_authenticate(self.admin)

    def _preview(self, **payload):
        return self.client.post(
            "/api/communication/blasts/preview/",
            {"body": "Notice", "audience": "SCHOOL", **payload},
            format="json",
        )

    def test_whole_school_reaches_every_parent(self):
        res = self._preview()
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["recipients"], 2)

    def test_one_class_reaches_only_that_class(self):
        res = self._preview(audience="GRADE", grade=7)
        self.assertEqual(res.data["recipients"], 1)
        self.assertEqual(res.data["sample"][0]["name"], self.parent_b.full_name)

    def test_a_stream_narrows_the_class_further(self):
        make_learner(self.school, grade=7, stream="North").guardians.add(
            make_guardian(self.school, phone="0744000333")
        )
        both = self._preview(audience="GRADE", grade=7)
        self.assertEqual(both.data["recipients"], 2)
        one = self._preview(audience="GRADE", grade=7, stream="South")
        self.assertEqual(one.data["recipients"], 1)

    def test_a_family_with_two_children_is_one_phone_not_two(self):
        """The school pays per message; a parent should not be told twice."""
        second_child = make_learner(self.school, grade=3)
        second_child.guardians.add(self.parent_a)
        res = self._preview()
        self.assertEqual(res.data["recipients"], 2)

    def test_a_parent_with_no_phone_is_skipped_rather_than_sent_to_nothing(self):
        make_guardian(self.school, [self.g5], phone="")
        res = self._preview()
        self.assertEqual(res.data["recipients"], 2)

    def test_numbers_are_normalised_for_the_gateway(self):
        res = self._preview(audience="GRADE", grade=5)
        self.assertEqual(res.data["sample"][0]["phone"], "254722000111")

    def test_only_parents_of_this_school_are_reached(self):
        elsewhere = make_school("Elsewhere")
        make_guardian(elsewhere, [make_learner(elsewhere, grade=5)], phone="0755000444")
        res = self._preview()
        self.assertEqual(res.data["recipients"], 2)

    def test_a_left_learner_no_longer_pulls_their_parent_in(self):
        self.g7.active = False
        self.g7.save(update_fields=["active"])
        res = self._preview()
        self.assertEqual(res.data["recipients"], 1)


class FeeReminderTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        self.owing = make_learner(self.school, grade=5, stream="North")
        self.paid = make_learner(self.school, grade=5, stream="North")
        self.parent_owing = make_guardian(self.school, [self.owing], phone="0722000111")
        make_guardian(self.school, [self.paid], phone="0733000222")
        structure = FeeStructure.objects.create(
            school=self.school, grade=5, term=1, year=2026, amount=Decimal("12000")
        )
        Invoice.objects.create(
            school=self.school, learner=self.owing, fee_structure=structure,
            amount_due=Decimal("12000"), amount_paid=Decimal("2000"),
        )
        Invoice.objects.create(
            school=self.school, learner=self.paid, fee_structure=structure,
            amount_due=Decimal("12000"), amount_paid=Decimal("12000"),
        )
        self.client.force_authenticate(self.admin)

    def test_the_unpaid_audience_skips_families_who_have_cleared(self):
        res = self.client.post(
            "/api/communication/blasts/preview/",
            {"body": "Kindly clear", "audience": "UNPAID"},
            format="json",
        )
        self.assertEqual(res.data["recipients"], 1)
        self.assertEqual(res.data["sample"][0]["name"], self.parent_owing.full_name)

    def test_merge_fields_give_each_family_their_own_figures(self):
        res = self.client.post(
            "/api/communication/blasts/preview/",
            {
                "body": "Dear {name}, {learner} of {class} owes KES {balance}. {school}",
                "audience": "UNPAID",
            },
            format="json",
        )
        text = res.data["sample"][0]["text"]
        self.assertIn(self.parent_owing.full_name, text)
        self.assertIn(self.owing.full_name, text)
        self.assertIn("10,000", text)
        self.assertIn(self.school.name, text)
        self.assertNotIn("{", text)


class SendingTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        self.learner = make_learner(self.school, grade=5)
        make_guardian(self.school, [self.learner], phone="0722000111")

    def test_sending_writes_one_message_per_parent_against_the_blast(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            "/api/communication/blasts/",
            {"title": "Closing day", "body": "School closes Friday.",
             "audience": "SCHOOL", "channel": "SMS"},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        blast = MessageBlast.objects.get(pk=res.data["id"])
        self.assertEqual(blast.recipients, 1)
        self.assertEqual(blast.sent_by_id, self.admin.id)
        message = SmsMessage.objects.get(blast=blast)
        self.assertEqual(message.recipient, "254722000111")
        # No gateway configured in tests: logged, not silently dropped.
        self.assertEqual(message.status, SmsMessage.Status.STUBBED)

    def test_whatsapp_goes_out_on_its_own_channel(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            "/api/communication/blasts/",
            {"body": "Meeting on Monday.", "audience": "SCHOOL", "channel": "WHATSAPP"},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        message = SmsMessage.objects.get(blast_id=res.data["id"])
        self.assertEqual(message.channel, "WHATSAPP")

    def test_the_history_shows_what_was_delivered(self):
        self.client.force_authenticate(self.admin)
        self.client.post(
            "/api/communication/blasts/",
            {"body": "Notice", "audience": "SCHOOL"},
            format="json",
        )
        res = self.client.get("/api/communication/blasts/")
        self.assertEqual(res.data["results"][0]["delivery"], {"STUBBED": 1})

    def test_a_blast_needs_a_message(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            "/api/communication/blasts/",
            {"body": "   ", "audience": "SCHOOL"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_messaging_one_class_needs_the_class_named(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            "/api/communication/blasts/",
            {"body": "Notice", "audience": "GRADE"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("grade", res.data)


class WhoMaySendTests(APITestCase):
    """The school's megaphone costs money and speaks in the school's name."""

    def setUp(self):
        self.school = make_school()
        self.learner = make_learner(self.school, grade=5)
        make_guardian(self.school, [self.learner], phone="0722000111")

    def _try_send(self, user):
        self.client.force_authenticate(user)
        return self.client.post(
            "/api/communication/blasts/",
            {"body": "Notice", "audience": "SCHOOL"},
            format="json",
        )

    def test_the_head_teacher_may_send(self):
        head = make_teacher(self.school, rank="HEAD")
        self.assertEqual(self._try_send(head.user).status_code, 201)

    def test_the_bursar_may_send(self):
        bursar = make_support(self.school, category="BURSAR")
        self.assertEqual(self._try_send(bursar.user).status_code, 201)

    def test_a_class_teacher_may_not(self):
        teacher = make_teacher(self.school, rank="TEACHER")
        self.assertEqual(self._try_send(teacher.user).status_code, 403)

    def test_a_parent_may_not(self):
        parent = make_user(self.school, "PARENT")
        self.assertEqual(self._try_send(parent).status_code, 403)

    def test_a_teacher_cannot_read_the_blast_history_either(self):
        teacher = make_teacher(self.school, rank="TEACHER")
        self.client.force_authenticate(teacher.user)
        self.assertEqual(self.client.get("/api/communication/blasts/").status_code, 403)
