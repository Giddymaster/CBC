"""Bulk imports for the staff room and the school's facilities."""

import io

from rest_framework.test import APITestCase

from apps.facilities.models import Facility, FacilityAssignment
from apps.students.models import ClassGroup
from apps.teachers.models import SupportStaff, Teacher
from tests.factories import make_learning_area, make_school, make_teacher, make_user

STAFF_CSV = (
    "Type,First Name,Last Name,Gender,TSC / Payroll No,Phone,Employment,"
    "Category,Rank / Title,Subjects,Class Teacher Of\n"
    "Teaching,Jane,Wanjiku,F,412001,254700000001,TSC,,Senior Teacher,"
    "Mathematics; Kiswahili,G4 North\n"
    "Teaching,Paul,Otieno,M,412002,254700000002,BOM,,Teacher,Mathematics,\n"
    "Non-teaching,Esther,Nafula,F,,254700000003,BOM,Kitchen staff,Head Cook,,\n"
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

    def test_a_duplicate_tsc_number_is_reported_not_written(self):
        make_teacher(self.school, tsc_number="412001")
        self.client.force_authenticate(self.admin)
        res = upload(self.client, "/api/school/staff/bulk/", STAFF_CSV, commit=True)
        self.assertEqual(res.data["created"], 2)
        self.assertTrue(
            any("already on the register" in p["errors"][0] for p in res.data["problems"])
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
