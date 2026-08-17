"""CSV bulk import, photo downscaling, staff roll-call and lesson plans —
the features that had a model and no way in."""

import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.common.images import downscale_photo
from apps.students.models import AdmissionRight, Guardian, Learner
from apps.teachers.models import LessonPlan, SchemeOfWork, TeacherAttendance
from tests.factories import (
    make_learner,
    make_learning_area,
    make_school,
    make_teacher,
    make_user,
)

HEADER = "Adm No,First Name,Last Name,DOB,Sex,Class,Stream,Parent,Phone\n"


def csv_file(body, name="intake.csv"):
    return SimpleUploadedFile(name, (HEADER + body).encode("utf-8"), content_type="text/csv")


class BulkImportTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        self.teacher = make_teacher(self.school)
        self.client.force_authenticate(self.admin)

    def _post(self, body, commit=False, name="intake.csv"):
        data = {"file": csv_file(body, name)}
        if commit:
            data["commit"] = "true"
        return self.client.post("/api/admissions/bulk/", data, format="multipart")

    def test_a_dry_run_writes_nothing(self):
        res = self._post("ADM900,Wanjiru,Kamau,2019-04-12,F,Grade 1,North,Grace Kamau,254722000111\n")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["ready"], 1)
        self.assertFalse(res.data["committed"])
        self.assertEqual(Learner.objects.count(), 0)

    def test_committing_creates_the_learners(self):
        res = self._post(
            "ADM900,Wanjiru,Kamau,2019-04-12,F,Grade 1,North,Grace Kamau,254722000111\n"
            "ADM901,Otieno,Ochieng,2018-06-01,M,Grade 2,South,John Ochieng,254733000222\n",
            commit=True,
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["created"], 2)
        self.assertEqual(Learner.objects.count(), 2)
        self.assertEqual(Guardian.objects.count(), 2)

    def test_headers_are_recognised_however_the_school_spells_them(self):
        """'Adm No' and 'DOB' and 'Sex' and 'Class' all have to work."""
        res = self._post("ADM900,Wanjiru,Kamau,2019-04-12,F,Grade 1,North,,\n")
        self.assertIn("admission_number", res.data["recognised_columns"])
        self.assertIn("date_of_birth", res.data["recognised_columns"])
        self.assertIn("gender", res.data["recognised_columns"])
        self.assertIn("grade", res.data["recognised_columns"])

    def test_several_date_formats_are_accepted(self):
        res = self._post(
            "ADM900,A,One,2019-04-12,F,1,,,\n"
            "ADM901,B,Two,12/04/2019,M,1,,,\n"
            "ADM902,C,Three,12.04.2019,F,1,,,\n",
            commit=True,
        )
        self.assertEqual(res.data["created"], 3)

    def test_grade_words_are_understood(self):
        res = self._post(
            "ADM900,A,One,2019-04-12,F,PP1,,,\n"
            "ADM901,B,Two,2019-04-12,M,G4,,,\n"
            "ADM902,C,Three,2019-04-12,F,7,,,\n",
            commit=True,
        )
        self.assertEqual(res.data["created"], 3)
        self.assertCountEqual(
            list(Learner.objects.values_list("grade", flat=True)), [-1, 4, 7]
        )

    def test_a_bad_row_is_reported_with_its_line_number(self):
        res = self._post(
            "ADM900,Wanjiru,Kamau,2019-04-12,F,Grade 1,North,,\n"
            "ADM901,,Nameless,2019-04-12,M,Grade 1,,,\n"
            "ADM902,Bad,Date,31/02/2019,F,Grade 1,,,\n"
        )
        self.assertEqual(res.data["ready"], 1)
        rows = {p["row"] for p in res.data["problems"]}
        self.assertEqual(rows, {3, 4})  # row 1 is the header
        joined = " ".join(e for p in res.data["problems"] for e in p["errors"])
        self.assertIn("first name is missing", joined)
        self.assertIn("not a date", joined)

    def test_good_rows_still_import_when_others_fail(self):
        res = self._post(
            "ADM900,Wanjiru,Kamau,2019-04-12,F,Grade 1,North,,\n"
            "ADM901,,Nameless,2019-04-12,M,Grade 1,,,\n",
            commit=True,
        )
        self.assertEqual(res.data["created"], 1)
        self.assertEqual(len(res.data["problems"]), 1)

    def test_a_duplicate_inside_the_file_is_caught(self):
        res = self._post(
            "ADM900,A,One,2019-04-12,F,1,,,\n"
            "ADM900,B,Two,2019-04-12,M,1,,,\n"
        )
        joined = " ".join(e for p in res.data["problems"] for e in p["errors"])
        self.assertIn("appears twice", joined)

    def test_a_number_already_on_the_register_is_caught(self):
        make_learner(self.school, admission_number="ADM900")
        res = self._post("ADM900,A,One,2019-04-12,F,1,,,\n")
        joined = " ".join(e for p in res.data["problems"] for e in p["errors"])
        self.assertIn("already enrolled", joined)

    def test_a_blank_admission_number_continues_the_sequence(self):
        make_learner(self.school, admission_number="ADM0281")
        res = self._post(",A,One,2019-04-12,F,1,,,\n", commit=True)
        self.assertEqual(res.data["created"], 1)
        self.assertTrue(
            Learner.objects.filter(admission_number="ADM0282").exists()
        )

    def test_a_file_missing_required_columns_is_refused(self):
        upload = SimpleUploadedFile(
            "bad.csv", b"Nickname,Colour\nBobby,Blue\n", content_type="text/csv"
        )
        res = self.client.post(
            "/api/admissions/bulk/", {"file": upload}, format="multipart"
        )
        self.assertEqual(res.data["ready"], 0)
        self.assertIn("first name", res.data["problems"][0]["errors"][0])

    def test_committing_a_file_with_no_usable_rows_is_a_400(self):
        res = self._post("ADM900,,Nameless,2019-04-12,M,Grade 1,,,\n", commit=True)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(Learner.objects.count(), 0)

    def test_a_teacher_without_admission_rights_cannot_import(self):
        self.client.force_authenticate(self.teacher.user)
        res = self._post("ADM900,A,One,2019-04-12,F,1,,,\n")
        self.assertEqual(res.status_code, 403)

    def test_a_delegate_can_import(self):
        AdmissionRight.objects.create(
            school=self.school, user=self.teacher.user, granted_by=self.admin
        )
        self.client.force_authenticate(self.teacher.user)
        res = self._post("ADM900,A,One,2019-04-12,F,1,,,\n", commit=True)
        self.assertEqual(res.status_code, 201)

    def test_a_template_can_be_downloaded(self):
        res = self.client.get("/api/admissions/bulk/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("First Name", res.content.decode())

    def test_a_sibling_in_the_file_reuses_one_guardian(self):
        self._post(
            "ADM900,A,Kamau,2019-04-12,F,1,,Grace Kamau,254722000111\n"
            "ADM901,B,Kamau,2017-04-12,M,3,,Grace Kamau,254722000111\n",
            commit=True,
        )
        self.assertEqual(Guardian.objects.filter(full_name="Grace Kamau").count(), 1)


class PhotoDownscaleTests(APITestCase):
    def _photo(self, size=(2400, 1600), colour=(65, 118, 144)):
        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGB", size, colour).save(buffer, format="PNG")
        buffer.seek(0)
        return SimpleUploadedFile("big.png", buffer.read(), content_type="image/png")

    def test_a_large_photo_is_shrunk(self):
        original = self._photo()
        original_size = original.size
        result = downscale_photo(original)
        self.assertLess(result.size, original_size)
        self.assertTrue(result.name.endswith(".jpg"))

    def test_it_is_cropped_square_for_the_circular_frame(self):
        from PIL import Image

        result = downscale_photo(self._photo(size=(2400, 1200)))
        image = Image.open(result)
        self.assertEqual(image.width, image.height)
        self.assertLessEqual(image.width, 512)

    def test_an_already_square_thumbnail_is_left_alone(self):
        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGB", (64, 64), (0, 0, 0)).save(buffer, format="PNG")
        buffer.seek(0)
        small = SimpleUploadedFile("small.png", buffer.read(), content_type="image/png")
        self.assertIs(downscale_photo(small), small)

    def test_a_small_but_wrongly_shaped_photo_is_still_cropped(self):
        """Few bytes is not the same as ready to display in a circle."""
        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGB", (400, 200), (0, 0, 0)).save(buffer, format="PNG")
        buffer.seek(0)
        oblong = SimpleUploadedFile("oblong.png", buffer.read(), content_type="image/png")
        result = downscale_photo(oblong)
        self.assertIsNot(result, oblong)
        image = Image.open(result)
        self.assertEqual(image.width, image.height)

    def test_a_file_that_is_not_an_image_is_rejected(self):
        # A file Pillow cannot decode must never be stored: an .svg or .html
        # kept under a photo field and served same-origin is stored XSS.
        junk = SimpleUploadedFile("x.png", b"x" * 80_000, content_type="image/png")
        with self.assertRaises(ValueError):
            downscale_photo(junk)

    def test_none_is_handled(self):
        self.assertIsNone(downscale_photo(None))

    def test_an_uploaded_learner_photo_is_stored_small(self):
        school = make_school()
        admin = make_user(school, "ADMIN")
        learner = make_learner(school)
        self.client.force_authenticate(admin)
        res = self.client.post(
            f"/api/learners/{learner.id}/photo/",
            {"photo": self._photo()},
            format="multipart",
        )
        self.assertEqual(res.status_code, 200)
        learner.refresh_from_db()
        self.assertLess(learner.photo.size, 200_000)


class StaffRollCallTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        self.head = make_teacher(self.school, rank="HEAD")
        self.teacher = make_teacher(self.school)
        self.client.force_authenticate(self.admin)

    def test_the_register_lists_every_active_teacher_unmarked(self):
        res = self.client.get("/api/staff/roll-call/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data["staff"]), 2)
        self.assertEqual(res.data["totals"]["not_marked"], 2)

    def test_marking_the_register(self):
        res = self.client.post(
            "/api/staff/roll-call/",
            {"records": [
                {"teacher": self.head.id, "status": "P"},
                {"teacher": self.teacher.id, "status": "A"},
            ]},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data["saved"]), 2)
        self.assertEqual(TeacherAttendance.objects.count(), 2)

    def test_correcting_the_register_does_not_duplicate(self):
        body = {"records": [{"teacher": self.teacher.id, "status": "A"}]}
        self.client.post("/api/staff/roll-call/", body, format="json")
        self.client.post(
            "/api/staff/roll-call/",
            {"records": [{"teacher": self.teacher.id, "status": "P"}]},
            format="json",
        )
        self.assertEqual(TeacherAttendance.objects.count(), 1)
        self.assertEqual(TeacherAttendance.objects.get().status, "P")

    def test_a_bad_status_is_skipped_not_stored(self):
        res = self.client.post(
            "/api/staff/roll-call/",
            {"records": [{"teacher": self.teacher.id, "status": "Z"}]},
            format="json",
        )
        self.assertEqual(res.data["saved"], [])
        self.assertEqual(TeacherAttendance.objects.count(), 0)

    def test_another_schools_teacher_is_skipped(self):
        outsider = make_teacher(make_school("Elsewhere"))
        res = self.client.post(
            "/api/staff/roll-call/",
            {"records": [{"teacher": outsider.id, "status": "P"}]},
            format="json",
        )
        self.assertEqual(res.data["saved"], [])

    def test_the_head_teacher_may_take_it(self):
        self.client.force_authenticate(self.head.user)
        self.assertEqual(self.client.get("/api/staff/roll-call/").status_code, 200)

    def test_a_class_teacher_may_not(self):
        self.client.force_authenticate(self.teacher.user)
        self.assertEqual(self.client.get("/api/staff/roll-call/").status_code, 403)

    def test_a_junk_date_is_a_400(self):
        res = self.client.get("/api/staff/roll-call/?date=yesterday")
        self.assertEqual(res.status_code, 400)

    def test_the_register_defaults_to_the_schools_today(self):
        res = self.client.get("/api/staff/roll-call/")
        self.assertEqual(res.data["date"], timezone.localdate().isoformat())


class LessonPlanTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.teacher = make_teacher(self.school)
        self.other = make_teacher(self.school)
        self.maths = make_learning_area("Mathematics", "MATH")
        self.scheme = SchemeOfWork.objects.create(
            school=self.school, teacher=self.teacher, learning_area=self.maths,
            grade=7, term=1, year=2026,
            content={"weeks": [{"week": 1, "lessons": [{"lesson": 1}]}]},
        )

    def _payload(self, **extra):
        return {
            "week": 1, "lesson_number": 1, "strand": "Numbers",
            "sub_strand": "Whole numbers",
            "learning_outcomes": "Read and write numbers up to a million.",
            **extra,
        }

    def test_a_teacher_plans_a_lesson_on_their_own_scheme(self):
        self.client.force_authenticate(self.teacher.user)
        res = self.client.post(
            f"/api/schemes-of-work/{self.scheme.id}/lesson-plans/",
            self._payload(), format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(LessonPlan.objects.count(), 1)

    def test_replanning_the_same_lesson_edits_it(self):
        self.client.force_authenticate(self.teacher.user)
        url = f"/api/schemes-of-work/{self.scheme.id}/lesson-plans/"
        self.client.post(url, self._payload(), format="json")
        self.client.post(url, self._payload(strand="Algebra"), format="json")
        self.assertEqual(LessonPlan.objects.count(), 1)
        self.assertEqual(LessonPlan.objects.get().strand, "Algebra")

    def test_a_colleague_cannot_plan_on_someone_elses_scheme(self):
        self.client.force_authenticate(self.other.user)
        res = self.client.post(
            f"/api/schemes-of-work/{self.scheme.id}/lesson-plans/",
            self._payload(), format="json",
        )
        self.assertEqual(res.status_code, 403)

    def test_the_view_returns_the_schemes_weeks_alongside_the_plans(self):
        self.client.force_authenticate(self.teacher.user)
        res = self.client.get(f"/api/schemes-of-work/{self.scheme.id}/lesson-plans/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["weeks"][0]["week"], 1)

    def test_another_schools_scheme_is_out_of_reach(self):
        elsewhere = make_school("Elsewhere")
        outsider = SchemeOfWork.objects.create(
            school=elsewhere, teacher=make_teacher(elsewhere),
            learning_area=self.maths, grade=7, term=1, year=2026,
        )
        self.client.force_authenticate(self.teacher.user)
        res = self.client.get(f"/api/schemes-of-work/{outsider.id}/lesson-plans/")
        self.assertEqual(res.status_code, 403)
