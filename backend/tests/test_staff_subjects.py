"""A teacher's subjects on the staff register.

The Subjects column used to be derived only from timetable assignments, so it
could not be set when adding a teacher or corrected afterwards. Now it is a
real field on the record (Teacher.learning_areas), merged with whatever the
timetable also assigns.
"""

from rest_framework.test import APITestCase

from apps.teachers.models import Teacher
from apps.timetable.models import LessonRequirement
from tests.factories import (
    make_learning_area,
    make_school,
    make_teacher,
    make_user,
)


class StaffSubjectsTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        self.maths = make_learning_area("Mathematics", "MATH")
        self.kiswahili = make_learning_area("Kiswahili", "KIS")

    def test_adding_a_teacher_with_subjects_stores_and_lists_them(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            "/api/school/staff/add-teacher/",
            {
                "first_name": "Amina", "last_name": "Yusuf",
                "tsc_number": "TSC777001", "employment_type": "TSC",
                "learning_areas": [self.maths.id, self.kiswahili.id],
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        teacher = Teacher.objects.get(tsc_number="TSC777001")
        self.assertEqual(
            set(teacher.learning_areas.values_list("id", flat=True)),
            {self.maths.id, self.kiswahili.id},
        )
        directory = self.client.get("/api/school/staff/").data
        row = next(t for t in directory["teaching"] if t["id"] == teacher.id)
        self.assertEqual(row["subjects"], ["Kiswahili", "Mathematics"])
        self.assertEqual(
            set(row["learning_area_ids"]), {self.maths.id, self.kiswahili.id}
        )

    def test_editing_replaces_the_subject_set(self):
        teacher = make_teacher(self.school)
        teacher.learning_areas.set([self.maths])
        self.client.force_authenticate(self.admin)
        res = self.client.patch(
            f"/api/school/staff/teachers/{teacher.id}/",
            {"learning_areas": [self.kiswahili.id]},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(
            list(teacher.learning_areas.values_list("name", flat=True)),
            ["Kiswahili"],
        )

    def test_subjects_merge_with_timetable_assignments(self):
        """Record says Kiswahili, timetable says Mathematics — the register
        shows both, without duplicates."""
        teacher = make_teacher(self.school)
        teacher.learning_areas.set([self.kiswahili])
        LessonRequirement.objects.create(
            school=self.school, teacher=teacher, learning_area=self.maths,
            grade=5, lessons_per_week=5,
        )
        self.client.force_authenticate(self.admin)
        directory = self.client.get("/api/school/staff/").data
        row = next(t for t in directory["teaching"] if t["id"] == teacher.id)
        self.assertEqual(row["subjects"], ["Kiswahili", "Mathematics"])

    def test_the_directory_offers_the_national_subject_list(self):
        self.client.force_authenticate(self.admin)
        choices = self.client.get("/api/school/staff/").data["learning_area_choices"]
        names = [c["name"] for c in choices]
        self.assertIn("Mathematics", names)
        self.assertIn("Kiswahili", names)
