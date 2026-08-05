"""Admitting a learner, delegating that right, learner photos, and the
notification feed behind the topbar bell."""

from datetime import date, timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from apps.students.models import AdmissionRight, Guardian, Learner, can_admit
from apps.students.admissions import next_admission_number
from apps.teachers.models import StaffMessage, StaffReport, StaffTask
from tests.factories import (
    make_guardian,
    make_learner,
    make_school,
    make_support,
    make_teacher,
    make_user,
)

# A 1x1 GIF — smallest thing Pillow will accept as a real image.
TINY_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!"
    b"\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


def admission_payload(**overrides):
    payload = {
        "first_name": "Wanjiru",
        "last_name": "Kamau",
        "date_of_birth": "2019-04-12",
        "gender": "F",
        "grade": 1,
        "stream": "North",
        "birth_certificate_no": "BC-2019-4412",
        "nationality": "Kenyan",
        "religion": "Christian",
        "county": "Kiambu",
        "subcounty": "Ruiru",
        "home_address": "Membley Estate, House 22",
        "residence": "DAY",
        "transport": "BUS",
        "bus_route": "Route 3 — Membley",
        "blood_group": "O+",
        "allergies": "Peanuts",
        "chronic_conditions": "Mild asthma",
        "medication": "Salbutamol inhaler as needed",
        "immunisation_up_to_date": True,
        "special_needs": "Needs to sit near the front",
        "previous_school": "Little Angels Academy",
        "emergency_contact_name": "Peter Kamau",
        "emergency_contact_phone": "254711000111",
        "emergency_contact_relationship": "Uncle",
        "guardians": [
            {
                "full_name": "Grace Kamau",
                "phone": "254722000111",
                "relationship": "MOTHER",
                "national_id": "23456789",
                "occupation": "Nurse",
                "is_primary_contact": True,
            },
            {"full_name": "John Kamau", "phone": "254733000222", "relationship": "FATHER"},
        ],
    }
    payload.update(overrides)
    return payload


class AdmissionTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        self.teacher = make_teacher(self.school)

    def test_admin_admits_a_learner_with_the_whole_form(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post("/api/admissions/", admission_payload(), format="json")
        self.assertEqual(res.status_code, 201, res.data)

        learner = Learner.objects.get(pk=res.data["id"])
        self.assertEqual(learner.full_name, "Wanjiru Kamau")
        self.assertEqual(learner.blood_group, "O+")
        self.assertEqual(learner.allergies, "Peanuts")
        self.assertEqual(learner.bus_route, "Route 3 — Membley")
        self.assertEqual(learner.emergency_contact_phone, "254711000111")
        self.assertEqual(learner.admitted_by_id, self.admin.id)
        self.assertEqual(learner.admission_date, date.today())
        self.assertEqual(learner.guardians.count(), 2)
        self.assertTrue(learner.guardians.filter(is_primary_contact=True).exists())

    def test_admission_number_is_generated_when_left_blank(self):
        make_learner(self.school, admission_number="ADM0281")
        self.client.force_authenticate(self.admin)
        res = self.client.post("/api/admissions/", admission_payload(), format="json")
        self.assertEqual(res.data["admission_number"], "ADM0282")

    def test_first_ever_admission_number(self):
        self.assertEqual(next_admission_number(self.school), "ADM001")

    def test_an_explicit_duplicate_number_is_rejected(self):
        make_learner(self.school, admission_number="ADM0007")
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            "/api/admissions/", admission_payload(admission_number="ADM0007"), format="json"
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("admission_number", res.data)

    def test_a_sibling_reuses_the_same_guardian_record(self):
        self.client.force_authenticate(self.admin)
        self.client.post("/api/admissions/", admission_payload(), format="json")
        self.client.post(
            "/api/admissions/",
            admission_payload(first_name="Njeri", grade=3),
            format="json",
        )
        self.assertEqual(Guardian.objects.filter(full_name="Grace Kamau").count(), 1)
        self.assertEqual(
            Guardian.objects.get(full_name="Grace Kamau").learners.count(), 2
        )

    def test_a_failed_admission_leaves_nothing_behind(self):
        self.client.force_authenticate(self.admin)
        before = Guardian.objects.count()
        res = self.client.post(
            "/api/admissions/",
            admission_payload(date_of_birth="not-a-date"),
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(Learner.objects.count(), 0)
        self.assertEqual(Guardian.objects.count(), before)

    def test_a_plain_teacher_cannot_admit(self):
        self.client.force_authenticate(self.teacher.user)
        res = self.client.post("/api/admissions/", admission_payload(), format="json")
        self.assertEqual(res.status_code, 403)
        self.assertEqual(Learner.objects.count(), 0)

    def test_a_parent_cannot_admit(self):
        parent = make_user(self.school, "PARENT")
        self.client.force_authenticate(parent)
        res = self.client.post("/api/admissions/", admission_payload(), format="json")
        self.assertEqual(res.status_code, 403)


class DelegationTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        self.head = make_teacher(self.school, rank="HEAD")
        self.class_teacher = make_teacher(self.school)
        self.cook = make_support(self.school, category="KITCHEN")

    def _delegate_to(self, user, **extra):
        self.client.force_authenticate(self.admin)
        return self.client.post(
            "/api/admission-rights/", {"user": user.id, **extra}, format="json"
        )

    def test_admin_delegates_to_the_head_teacher(self):
        res = self._delegate_to(self.head.user, note="Grade 1 intake 2027")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertTrue(can_admit(self.head.user))

    def test_a_delegate_can_then_admit(self):
        self._delegate_to(self.class_teacher.user)
        self.client.force_authenticate(self.class_teacher.user)
        res = self.client.post("/api/admissions/", admission_payload(), format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(
            Learner.objects.get().admitted_by_id, self.class_teacher.user_id
        )

    def test_revoking_the_right_stops_admissions(self):
        self._delegate_to(self.class_teacher.user)
        right = AdmissionRight.objects.get(user=self.class_teacher.user)
        self.client.force_authenticate(self.admin)
        self.client.delete(f"/api/admission-rights/{right.id}/")
        right.refresh_from_db()
        self.assertFalse(right.active)

        self.client.force_authenticate(self.class_teacher.user)
        res = self.client.post("/api/admissions/", admission_payload(), format="json")
        self.assertEqual(res.status_code, 403)

    def test_an_expired_grant_stops_admissions(self):
        self._delegate_to(
            self.class_teacher.user,
            expires_on=(date.today() - timedelta(days=1)).isoformat(),
        )
        self.assertFalse(can_admit(self.class_teacher.user))

    def test_a_grant_expiring_today_still_works(self):
        self._delegate_to(self.class_teacher.user, expires_on=date.today().isoformat())
        self.assertTrue(can_admit(self.class_teacher.user))

    def test_non_teaching_staff_can_be_delegated(self):
        """A secretary handling the intake desk is a normal arrangement."""
        res = self._delegate_to(self.cook.user)
        self.assertEqual(res.status_code, 201)

    def test_a_teacher_cannot_delegate_to_themselves(self):
        self.client.force_authenticate(self.class_teacher.user)
        res = self.client.post(
            "/api/admission-rights/", {"user": self.class_teacher.user_id}, format="json"
        )
        self.assertEqual(res.status_code, 403)
        self.assertFalse(can_admit(self.class_teacher.user))

    def test_cannot_delegate_to_another_schools_staff(self):
        outsider = make_teacher(make_school("Elsewhere"))
        res = self._delegate_to(outsider.user)
        self.assertEqual(res.status_code, 400)

    def test_cannot_delegate_to_a_parent(self):
        parent = make_user(self.school, "PARENT")
        res = self._delegate_to(parent)
        self.assertEqual(res.status_code, 400)

    def test_access_endpoint_tells_the_ui_what_to_show(self):
        self.client.force_authenticate(self.class_teacher.user)
        before = self.client.get("/api/admissions/access/")
        self.assertFalse(before.data["can_admit"])

        self._delegate_to(self.class_teacher.user, note="Grade 1 intake")
        self.client.force_authenticate(self.class_teacher.user)
        after = self.client.get("/api/admissions/access/")
        self.assertTrue(after.data["can_admit"])
        self.assertEqual(after.data["note"], "Grade 1 intake")
        self.assertEqual(after.data["reason"], "Delegated by the school admin")


class LearnerPhotoTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        self.teacher = make_teacher(self.school)
        self.learner = make_learner(self.school)

    def _upload(self):
        return self.client.post(
            f"/api/learners/{self.learner.id}/photo/",
            {"photo": SimpleUploadedFile("face.gif", TINY_GIF, content_type="image/gif")},
            format="multipart",
        )

    def test_admin_uploads_a_learner_photo(self):
        self.client.force_authenticate(self.admin)
        res = self._upload()
        self.assertEqual(res.status_code, 200, res.data)
        self.learner.refresh_from_db()
        self.assertTrue(self.learner.photo)

    def test_photo_shows_on_the_learner_record(self):
        self.client.force_authenticate(self.admin)
        self._upload()
        res = self.client.get(f"/api/learners/{self.learner.id}/")
        self.assertTrue(res.data["photo"])

    def test_a_teacher_without_admission_rights_cannot_change_the_photo(self):
        self.client.force_authenticate(self.teacher.user)
        self.assertEqual(self._upload().status_code, 403)

    def test_photo_cannot_be_set_on_another_schools_learner(self):
        outsider = make_learner(make_school("Elsewhere"))
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            f"/api/learners/{outsider.id}/photo/",
            {"photo": SimpleUploadedFile("face.gif", TINY_GIF, content_type="image/gif")},
            format="multipart",
        )
        self.assertEqual(res.status_code, 403)

    def test_photo_can_be_removed(self):
        self.client.force_authenticate(self.admin)
        self._upload()
        res = self.client.delete(f"/api/learners/{self.learner.id}/photo/")
        self.assertEqual(res.status_code, 204)
        self.learner.refresh_from_db()
        self.assertFalse(self.learner.photo)


class LearnerPrivacyTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.parent_user = make_user(self.school, "PARENT")
        self.child = make_learner(self.school, blood_group="O+", allergies="Peanuts")
        make_guardian(self.school, learners=[self.child], user=self.parent_user)

    def test_a_parent_does_not_receive_medical_detail_over_the_list_api(self):
        self.client.force_authenticate(self.parent_user)
        res = self.client.get(f"/api/learners/{self.child.id}/")
        self.assertNotIn("allergies", res.data)
        self.assertNotIn("blood_group", res.data)
        self.assertNotIn("guardians_detail", res.data)

    def test_staff_do_receive_it(self):
        admin = make_user(self.school, "ADMIN")
        self.client.force_authenticate(admin)
        res = self.client.get(f"/api/learners/{self.child.id}/")
        self.assertEqual(res.data["allergies"], "Peanuts")


class NotificationTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.head = make_teacher(self.school, rank="HEAD")
        self.cook = make_support(self.school, category="KITCHEN", supervisor=self.head.user)

    def test_a_supervisor_message_appears_in_the_feed(self):
        StaffMessage.objects.create(
            school=self.school, sender=self.head.user, recipient=self.cook.user,
            body="Please confirm the flour order.",
        )
        self.client.force_authenticate(self.cook.user)
        res = self.client.get("/api/notifications/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["count"], 1)
        item = res.data["items"][0]
        self.assertEqual(item["kind"], "MESSAGE")
        self.assertIn(self.head.user.get_full_name(), item["title"])
        self.assertEqual(item["body"], "Please confirm the flour order.")

    def test_assigned_work_appears(self):
        StaffTask.objects.create(
            school=self.school, assigned_to=self.cook.user, assigned_by=self.head.user,
            title="Deep clean the store", due_date=date.today() - timedelta(days=2),
        )
        self.client.force_authenticate(self.cook.user)
        res = self.client.get("/api/notifications/")
        item = next(i for i in res.data["items"] if i["kind"] == "TASK")
        self.assertEqual(item["body"], "Deep clean the store")
        self.assertTrue(item["overdue"])

    def test_a_report_awaiting_my_approval_appears(self):
        StaffReport.objects.create(
            school=self.school, author=self.cook.user, supervisor=self.head.user,
            title="Kitchen weekly", status=StaffReport.Status.SUBMITTED,
        )
        self.client.force_authenticate(self.head.user)
        res = self.client.get("/api/notifications/")
        self.assertEqual(res.data["items"][0]["kind"], "REVIEW")

    def test_a_returned_report_tells_the_author(self):
        StaffReport.objects.create(
            school=self.school, author=self.cook.user, supervisor=self.head.user,
            title="Kitchen weekly", status=StaffReport.Status.RETURNED,
            review_comment="Add the stock figures.",
        )
        self.client.force_authenticate(self.cook.user)
        res = self.client.get("/api/notifications/")
        item = res.data["items"][0]
        self.assertEqual(item["kind"], "RETURNED")
        self.assertIn("Add the stock figures.", item["body"])

    def test_marking_read_clears_messages_but_not_outstanding_work(self):
        StaffMessage.objects.create(
            school=self.school, sender=self.head.user, recipient=self.cook.user, body="Hello",
        )
        StaffTask.objects.create(
            school=self.school, assigned_to=self.cook.user, assigned_by=self.head.user,
            title="Still to do",
        )
        self.client.force_authenticate(self.cook.user)
        self.client.post("/api/notifications/", {}, format="json")
        res = self.client.get("/api/notifications/")
        kinds = [i["kind"] for i in res.data["items"]]
        self.assertNotIn("MESSAGE", kinds)
        self.assertIn("TASK", kinds)

    def test_i_never_see_someone_elses_notifications(self):
        other = make_support(self.school, category="CLEANER", supervisor=self.head.user)
        StaffMessage.objects.create(
            school=self.school, sender=self.head.user, recipient=other.user, body="Private",
        )
        self.client.force_authenticate(self.cook.user)
        res = self.client.get("/api/notifications/")
        self.assertEqual(res.data["count"], 0)
