"""Parent–teacher messaging: the first channel crossing the staff/parent line."""

from rest_framework.test import APITestCase

from apps.communication.models import ParentMessage
from apps.communication.parent_messages import staff_for_learner
from apps.students.models import ClassGroup
from tests.factories import (
    make_guardian,
    make_learner,
    make_school,
    make_support,
    make_teacher,
    make_user,
)


class ContactTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.class_teacher = make_teacher(self.school)
        self.head = make_teacher(self.school, rank="HEAD")
        self.stranger = make_teacher(self.school)
        self.learner = make_learner(self.school, grade=5, stream="North")
        ClassGroup.objects.create(
            school=self.school, grade=5, stream="North",
            class_teacher=self.class_teacher,
        )

    def test_the_class_teacher_and_head_are_reachable(self):
        ids = {c["user_id"] for c in staff_for_learner(self.learner)}
        self.assertIn(self.class_teacher.user_id, ids)
        self.assertIn(self.head.user_id, ids)

    def test_an_unrelated_teacher_is_not(self):
        ids = {c["user_id"] for c in staff_for_learner(self.learner)}
        self.assertNotIn(self.stranger.user_id, ids)

    def test_a_class_with_no_teacher_still_reaches_the_head(self):
        orphan = make_learner(self.school, grade=8)
        ids = {c["user_id"] for c in staff_for_learner(orphan)}
        self.assertEqual(ids, {self.head.user_id})

    def test_the_class_teacher_is_labelled_as_such(self):
        contact = next(
            c for c in staff_for_learner(self.learner)
            if c["user_id"] == self.class_teacher.user_id
        )
        self.assertEqual(contact["role"], "Class teacher")


class MessagingTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.class_teacher = make_teacher(self.school)
        self.head = make_teacher(self.school, rank="HEAD")
        self.stranger = make_teacher(self.school)
        self.cook = make_support(self.school)

        self.child = make_learner(self.school, grade=5, stream="North")
        ClassGroup.objects.create(
            school=self.school, grade=5, stream="North",
            class_teacher=self.class_teacher,
        )
        self.parent_user = make_user(self.school, "PARENT")
        self.guardian = make_guardian(
            self.school, learners=[self.child], user=self.parent_user
        )

        self.other_child = make_learner(self.school, grade=5, stream="North")
        self.other_parent = make_user(self.school, "PARENT", username="otherparent")
        self.other_guardian = make_guardian(
            self.school, learners=[self.other_child], user=self.other_parent
        )

    def _send(self, *, learner=None, guardian=None, staff=None, body="Hello"):
        return self.client.post(
            "/api/communication/parent-messages/",
            {
                "learner": (learner or self.child).id,
                "guardian": (guardian or self.guardian).id,
                "staff": (staff or self.class_teacher).user_id,
                "body": body,
            },
            format="json",
        )

    def test_a_parent_writes_to_their_childs_class_teacher(self):
        self.client.force_authenticate(self.parent_user)
        res = self._send(body="Is Wanjiru settling in?")
        self.assertEqual(res.status_code, 201, res.data)
        message = ParentMessage.objects.get()
        self.assertEqual(message.sender_id, self.parent_user.id)
        self.assertTrue(message.from_parent)

    def test_a_parent_may_also_write_to_the_head(self):
        self.client.force_authenticate(self.parent_user)
        self.assertEqual(self._send(staff=self.head).status_code, 201)

    def test_a_parent_cannot_write_to_an_unrelated_teacher(self):
        self.client.force_authenticate(self.parent_user)
        self.assertEqual(self._send(staff=self.stranger).status_code, 403)

    def test_a_parent_cannot_write_about_someone_elses_child(self):
        self.client.force_authenticate(self.parent_user)
        res = self._send(learner=self.other_child)
        self.assertIn(res.status_code, (400, 403))
        self.assertEqual(ParentMessage.objects.count(), 0)

    def test_a_parent_cannot_pose_as_another_guardian(self):
        self.client.force_authenticate(self.parent_user)
        res = self._send(guardian=self.other_guardian, learner=self.other_child)
        self.assertEqual(res.status_code, 403)

    def test_a_parent_never_reads_another_familys_thread(self):
        ParentMessage.objects.create(
            school=self.school, learner=self.other_child, guardian=self.other_guardian,
            staff=self.class_teacher.user, sender=self.other_parent, body="Private",
        )
        self.client.force_authenticate(self.parent_user)
        res = self.client.get("/api/communication/parent-messages/")
        self.assertEqual(res.data["count"], 0)

    def test_the_teacher_replies_on_the_same_thread(self):
        self.client.force_authenticate(self.parent_user)
        self._send(body="Question")
        self.client.force_authenticate(self.class_teacher.user)
        res = self._send(body="Answer")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(ParentMessage.objects.count(), 2)
        self.assertFalse(ParentMessage.objects.last().from_parent)

    def test_a_teacher_sees_only_their_own_threads(self):
        ParentMessage.objects.create(
            school=self.school, learner=self.child, guardian=self.guardian,
            staff=self.head.user, sender=self.parent_user, body="For the head",
        )
        self.client.force_authenticate(self.stranger.user)
        self.assertEqual(
            self.client.get("/api/communication/parent-messages/").data["count"], 0
        )

    def test_messages_never_cross_the_school_border(self):
        elsewhere = make_school("Elsewhere")
        outsider = make_learner(elsewhere, grade=5)
        self.client.force_authenticate(self.parent_user)
        res = self._send(learner=outsider)
        self.assertEqual(res.status_code, 403)

    def test_a_guardian_not_recorded_for_the_child_is_rejected(self):
        loose = make_guardian(self.school)
        self.client.force_authenticate(make_user(self.school, "ADMIN"))
        res = self._send(guardian=loose)
        self.assertEqual(res.status_code, 400)


class ThreadViewTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.class_teacher = make_teacher(self.school)
        self.child = make_learner(self.school, grade=5, stream="North")
        ClassGroup.objects.create(
            school=self.school, grade=5, stream="North",
            class_teacher=self.class_teacher,
        )
        self.parent_user = make_user(self.school, "PARENT")
        self.guardian = make_guardian(
            self.school, learners=[self.child], user=self.parent_user
        )

    def _message(self, sender, body):
        return ParentMessage.objects.create(
            school=self.school, learner=self.child, guardian=self.guardian,
            staff=self.class_teacher.user, sender=sender, body=body,
        )

    def test_a_parent_sees_a_thread_per_child_and_contact(self):
        self.client.force_authenticate(self.parent_user)
        res = self.client.get("/api/parent/threads/")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["threads"])
        names = {t["staff_name"] for t in res.data["threads"]}
        self.assertIn(self.class_teacher.user.get_full_name(), names)

    def test_threads_are_offered_before_any_message_exists(self):
        """A parent needs somewhere to start the conversation."""
        self.client.force_authenticate(self.parent_user)
        res = self.client.get("/api/parent/threads/")
        self.assertEqual(res.data["threads"][0]["messages"], [])

    def test_a_thread_carries_the_ids_needed_to_reply(self):
        self.client.force_authenticate(self.parent_user)
        res = self.client.get("/api/parent/threads/")
        thread = res.data["threads"][0]
        for field in ("learner", "guardian", "staff"):
            self.assertIn(field, thread)
        self.assertEqual(res.data["guardian_id"], self.guardian.id)

    def test_a_thread_with_messages_sorts_above_an_empty_one(self):
        """The conversation the parent just had must not be buried under the
        contacts they have never written to."""
        head = make_teacher(self.school, rank="HEAD")
        self._message(self.parent_user, "Question for the class teacher")
        self.client.force_authenticate(self.parent_user)
        res = self.client.get("/api/parent/threads/")
        self.assertEqual(res.data["threads"][0]["staff"], self.class_teacher.user_id)
        self.assertTrue(res.data["threads"][0]["messages"])
        self.assertEqual(res.data["threads"][-1]["staff"], head.user_id)
        self.assertEqual(res.data["threads"][-1]["messages"], [])

    def test_opening_the_list_marks_staff_replies_as_read(self):
        message = self._message(self.class_teacher.user, "She is doing well")
        self.client.force_authenticate(self.parent_user)
        self.client.get("/api/parent/threads/")
        message.refresh_from_db()
        self.assertIsNotNone(message.read_at)

    def test_a_parents_own_message_is_not_marked_read_for_them(self):
        message = self._message(self.parent_user, "Question")
        self.client.force_authenticate(self.parent_user)
        self.client.get("/api/parent/threads/")
        message.refresh_from_db()
        self.assertIsNone(message.read_at)

    def test_staff_see_the_parents_who_wrote_to_them(self):
        self._message(self.parent_user, "Question")
        self.client.force_authenticate(self.class_teacher.user)
        res = self.client.get("/api/staff/parent-threads/")
        self.assertEqual(res.status_code, 200)
        thread = res.data["threads"][0]
        self.assertEqual(thread["learner_name"], self.child.full_name)
        self.assertEqual(thread["guardian_name"], self.guardian.full_name)

    def test_a_parent_cannot_use_the_staff_view(self):
        self.client.force_authenticate(self.parent_user)
        self.assertEqual(self.client.get("/api/staff/parent-threads/").status_code, 403)

    def test_a_non_parent_cannot_use_the_parent_view(self):
        self.client.force_authenticate(self.class_teacher.user)
        self.assertEqual(self.client.get("/api/parent/threads/").status_code, 403)

    def test_contacts_endpoint_lists_who_to_write_to(self):
        self.client.force_authenticate(self.parent_user)
        res = self.client.get(f"/api/learners/{self.child.id}/contacts/")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["contacts"])

    def test_a_parent_cannot_list_contacts_for_another_child(self):
        stranger = make_learner(self.school, grade=5)
        self.client.force_authenticate(self.parent_user)
        res = self.client.get(f"/api/learners/{stranger.id}/contacts/")
        self.assertEqual(res.status_code, 403)


class ParentNotificationTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.class_teacher = make_teacher(self.school)
        self.child = make_learner(self.school, grade=5, stream="North")
        ClassGroup.objects.create(
            school=self.school, grade=5, stream="North",
            class_teacher=self.class_teacher,
        )
        self.parent_user = make_user(self.school, "PARENT")
        self.guardian = make_guardian(
            self.school, learners=[self.child], user=self.parent_user
        )

    def test_a_parents_message_reaches_the_teachers_bell(self):
        """A teacher should not have to remember a second inbox."""
        ParentMessage.objects.create(
            school=self.school, learner=self.child, guardian=self.guardian,
            staff=self.class_teacher.user, sender=self.parent_user,
            body="Is she settling in?",
        )
        self.client.force_authenticate(self.class_teacher.user)
        res = self.client.get("/api/notifications/")
        item = next(i for i in res.data["items"] if i["kind"] == "PARENT")
        self.assertIn(self.child.full_name, item["title"])
        self.assertEqual(item["body"], "Is she settling in?")

    def test_a_teachers_own_reply_does_not_notify_them(self):
        ParentMessage.objects.create(
            school=self.school, learner=self.child, guardian=self.guardian,
            staff=self.class_teacher.user, sender=self.class_teacher.user,
            body="My own reply",
        )
        self.client.force_authenticate(self.class_teacher.user)
        res = self.client.get("/api/notifications/")
        self.assertFalse([i for i in res.data["items"] if i["kind"] == "PARENT"])

    def test_another_teacher_is_not_notified(self):
        other = make_teacher(self.school)
        ParentMessage.objects.create(
            school=self.school, learner=self.child, guardian=self.guardian,
            staff=self.class_teacher.user, sender=self.parent_user, body="Private",
        )
        self.client.force_authenticate(other.user)
        self.assertEqual(self.client.get("/api/notifications/").data["count"], 0)
