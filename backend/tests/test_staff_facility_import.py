"""Bulk imports for the staff room and the school's facilities."""

import io

from rest_framework.test import APITestCase

from apps.facilities.models import Facility, FacilityAssignment
from apps.students.models import ClassGroup
from apps.teachers.models import SupportStaff, Teacher
from tests.factories import make_learning_area, make_school, make_teacher, make_user

STAFF_CSV = (
    "Type,First Name,Last Name,Gender,TSC / Payroll No,Phone,Employment,"
    "Category,Rank / Title,Phase,Subjects,Class Teacher Of\n"
    "Teaching,Jane,Wanjiku,F,412001,254700000001,TSC,,Senior Teacher,Primary,"
    "Mathematics; Kiswahili,G4 North\n"
    "Teaching,Paul,Otieno,M,412002,254700000002,BOM,,Teacher,JSS,Mathematics,\n"
    "Non-teaching,Esther,Nafula,F,,254700000003,BOM,Kitchen staff,Head Cook,,,\n"
)


def upload(client, path, text, commit=False):
    payload = {"file": io.BytesIO(text.encode())}
    if commit:
        payload["commit"] = "true"
    return client.post(path, payload, format="multipart")


class StaffImportTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        make_learning_area("Mathematics", "MATH")
        make_learning_area("Kiswahili", "KIS")

    def test_dry_run_reports_without_writing(self):
        self.client.force_authenticate(self.admin)
        res = upload(self.client, "/api/school/staff/bulk/", STAFF_CSV)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["ready"], 3)
        self.assertEqual(res.data["problems"], [])
        self.assertFalse(Teacher.objects.exists())
        self.assertFalse(SupportStaff.objects.exists())

    def test_commit_creates_staff_logins_and_the_class_teacher(self):
        self.client.force_authenticate(self.admin)
        res = upload(self.client, "/api/school/staff/bulk/", STAFF_CSV, commit=True)
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["created"], 3)
        self.assertEqual(len(res.data["logins"]), 2)  # teaching rows only
        jane = Teacher.objects.get(tsc_number="412001")
        self.assertEqual(jane.rank, "SENIOR")
        self.assertEqual(jane.gender, "F")
        self.assertEqual(jane.phase, "PRIMARY")
        self.assertEqual(Teacher.objects.get(tsc_number="412002").phase, "JUNIOR")
        self.assertEqual(
            sorted(jane.learning_areas.values_list("name", flat=True)),
            ["Kiswahili", "Mathematics"],
        )
        self.assertTrue(jane.user.must_change_password)
        group = ClassGroup.objects.get(school=self.school, grade=4, stream="North")
        self.assertEqual(group.class_teacher_id, jane.id)
        esther = SupportStaff.objects.get(full_name="Esther Nafula")
        self.assertEqual(esther.category, "KITCHEN")
        self.assertEqual(esther.title, "Head Cook")

    def test_a_matching_tsc_updates_the_existing_teacher(self):
        """Re-importing the same file applies changes (a new Phase column, a
        corrected rank) to the people already registered, instead of rejecting
        them as duplicates."""
        existing = make_teacher(self.school, tsc_number="412001")
        existing.user.is_active = False  # was deactivated in the meantime
        existing.user.save(update_fields=["is_active"])
        self.client.force_authenticate(self.admin)

        dry = upload(self.client, "/api/school/staff/bulk/", STAFF_CSV)
        row = next(p for p in dry.data["preview"] if p["row"] == 2)
        self.assertEqual(row["action"], "Update")

        res = upload(self.client, "/api/school/staff/bulk/", STAFF_CSV, commit=True)
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["created"], 2)
        self.assertEqual(res.data["updated"], 1)
        # Updated teachers keep their login — a password is issued only for the
        # one newly created teaching row (Paul).
        self.assertEqual(len(res.data["logins"]), 1)
        existing.refresh_from_db()
        existing.user.refresh_from_db()
        self.assertEqual(existing.phase, "PRIMARY")
        self.assertEqual(existing.rank, "SENIOR")
        self.assertTrue(existing.user.is_active)  # the file reactivates them
        self.assertEqual(Teacher.objects.count(), 2)  # Jane updated, not duplicated

    def test_a_tsc_registered_at_another_school_is_still_blocked(self):
        other = make_school()
        make_teacher(other, tsc_number="412001")
        self.client.force_authenticate(self.admin)
        res = upload(self.client, "/api/school/staff/bulk/", STAFF_CSV, commit=True)
        self.assertEqual(res.data["created"], 2)
        self.assertTrue(
            any("another school" in p["errors"][0] for p in res.data["problems"])
        )

    def test_an_unknown_subject_blocks_the_row_with_advice(self):
        csv_text = STAFF_CSV.replace("Mathematics; Kiswahili", "Alchemy")
        self.client.force_authenticate(self.admin)
        res = upload(self.client, "/api/school/staff/bulk/", csv_text)
        self.assertEqual(res.data["ready"], 2)
        self.assertIn("Alchemy", res.data["problems"][0]["errors"][0])

    def test_a_teacher_cannot_import_staff(self):
        teacher = make_teacher(self.school)
        self.client.force_authenticate(teacher.user)
        res = upload(self.client, "/api/school/staff/bulk/", STAFF_CSV)
        self.assertEqual(res.status_code, 403)


class FacilityImportTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        self.cook = SupportStaff.objects.create(
            school=self.school, full_name="Esther Nafula",
            category="KITCHEN", title="Head Cook",
        )

    def test_import_creates_categories_facilities_and_assignments(self):
        csv_text = (
            "Facility,Category,Location,Capacity,Details,Condition,Staff Assigned\n"
            "Kitchen,Kitchen,Main block,,Feeds the lunch programme,Good,Esther Nafula\n"
            "Library,Library,Block B,120,2400 titles,Good,\n"
        )
        self.client.force_authenticate(self.admin)
        res = upload(self.client, "/api/facilities/bulk/", csv_text, commit=True)
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["created"], 2)
        kitchen = Facility.objects.get(name="Kitchen")
        self.assertEqual(kitchen.category.name, "Kitchen")
        self.assertIn("Condition: Good", kitchen.notes)
        assignment = FacilityAssignment.objects.get(facility=kitchen)
        self.assertEqual(assignment.support_staff_id, self.cook.id)
        self.assertEqual(assignment.position, "Head Cook")
        library = Facility.objects.get(name="Library")
        self.assertEqual(library.capacity, 120)

    def test_a_name_not_on_the_register_blocks_the_row(self):
        csv_text = (
            "Facility,Category,Details,Staff Assigned\n"
            "Sick Bay,Health,Two beds,Nurse Nobody\n"
        )
        self.client.force_authenticate(self.admin)
        res = upload(self.client, "/api/facilities/bulk/", csv_text)
        self.assertEqual(res.data["ready"], 0)
        self.assertIn("Nurse Nobody", res.data["problems"][0]["errors"][0])
