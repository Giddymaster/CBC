"""The School Profile page: contacts, crest, fee headings and the filing cabinet.

The school says who it is; the operator says who it is registered as. These
tests are mostly about that line — what a school admin may change about their
own school, and what they may not.
"""

import io

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from apps.schools.models import SchoolDocument
from tests.factories import make_school, make_teacher, make_user


def _png(size=(40, 40)):
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", size, (10, 80, 160)).save(buffer, format="PNG")
    return SimpleUploadedFile("crest.png", buffer.getvalue(), content_type="image/png")


class ProfileTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        self.teacher = make_teacher(self.school)

    def test_any_member_of_staff_may_read_the_office_number(self):
        self.school.contact_phone = "0722000111"
        self.school.save(update_fields=["contact_phone"])
        self.client.force_authenticate(self.teacher.user)
        res = self.client.get("/api/my-school/profile/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["contact_phone"], "0722000111")
        self.assertFalse(res.data["can_edit"])

    def test_the_admin_sets_the_contacts_and_motto(self):
        self.client.force_authenticate(self.admin)
        res = self.client.patch(
            "/api/my-school/profile/",
            {
                "contact_phone": "0722000111",
                "alt_phone": "0733000222",
                "contact_email": "office@school.ac.ke",
                "postal_address": "P.O. Box 42, Nyeri",
                "motto": "Education is light",
                "website": "school.ac.ke",
            },
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.school.refresh_from_db()
        self.assertEqual(self.school.motto, "Education is light")
        self.assertEqual(self.school.postal_address, "P.O. Box 42, Nyeri")

    def test_a_teacher_cannot_change_the_school(self):
        self.client.force_authenticate(self.teacher.user)
        res = self.client.patch(
            "/api/my-school/profile/", {"motto": "Mine now"}, format="json"
        )
        self.assertEqual(res.status_code, 403)

    def test_registration_facts_stay_with_the_operator(self):
        """A school renaming its own MoE code would break the register it is
        registered in — and the paybill prefix steers M-Pesa matching."""
        original_code = self.school.code
        self.client.force_authenticate(self.admin)
        res = self.client.patch(
            "/api/my-school/profile/",
            {"code": "FAKE999", "paybill_account_prefix": "XX", "motto": "Fine"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.school.refresh_from_db()
        self.assertEqual(self.school.code, original_code)
        self.assertEqual(self.school.paybill_account_prefix, "")
        self.assertEqual(self.school.motto, "Fine")

    def test_the_crest_is_uploaded_and_comes_back_as_a_url(self):
        self.client.force_authenticate(self.admin)
        res = self.client.patch(
            "/api/my-school/profile/", {"logo": _png()}, format="multipart"
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertTrue(res.data["logo_url"])
        self.school.refresh_from_db()
        self.assertTrue(self.school.logo)

    def test_a_school_admin_cannot_enrol_or_close_a_school(self):
        self.client.force_authenticate(self.admin)
        created = self.client.post(
            "/api/schools/", {"name": "Mine", "code": "NEW1", "county": "Nairobi"},
            format="json",
        )
        self.assertEqual(created.status_code, 403)
        deleted = self.client.delete(f"/api/schools/{self.school.id}/")
        self.assertEqual(deleted.status_code, 403)


class VoteHeadTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        self.client.force_authenticate(self.admin)

    def test_a_new_school_starts_with_the_common_headings(self):
        res = self.client.get("/api/my-school/profile/")
        self.assertIn("Tuition", res.data["fee_columns"])
        self.assertIn("Boarding", res.data["fee_columns"])

    def test_the_school_sets_its_own_headings(self):
        res = self.client.patch(
            "/api/my-school/profile/",
            {"vote_heads": ["Tuition", "Swimming", "Lunch"]},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["fee_columns"], ["Tuition", "Swimming", "Lunch"])

    def test_blanks_and_duplicates_are_tidied_away(self):
        res = self.client.patch(
            "/api/my-school/profile/",
            {"vote_heads": ["Tuition", "  ", "tuition", "Lunch", "Lunch"]},
            format="json",
        )
        self.assertEqual(res.data["fee_columns"], ["Tuition", "Lunch"])

    def test_a_new_heading_survives_a_term_nobody_has_priced_yet(self):
        """The bug this fixes: a column added but left empty used to vanish on
        the next load, because the grid was rebuilt from whatever amounts
        happened to be filled in."""
        self.client.patch(
            "/api/my-school/profile/",
            {"vote_heads": ["Tuition", "Swimming"]},
            format="json",
        )
        grid = self.client.get("/api/payments/fee-structures/grid/?term=1&year=2026")
        self.assertEqual(grid.data["columns"], ["Tuition", "Swimming"])

    def test_saving_the_grid_keeps_the_headings_it_was_saved_with(self):
        saved = self.client.post(
            "/api/payments/fee-structures/grid/",
            {
                "term": 1, "year": 2026,
                "columns": ["Tuition", "Swimming"],
                "rows": [{"grade": 5, "breakdown": {"Tuition": "10000"}}],
            },
            format="json",
        )
        self.assertEqual(saved.status_code, 200, saved.data)
        self.school.refresh_from_db()
        self.assertEqual(self.school.vote_heads, ["Tuition", "Swimming"])

    def test_a_removed_heading_still_shows_where_money_was_billed_under_it(self):
        """Dropping "Transport" from the list must not hide a term that was
        already priced with it — that money exists on invoices."""
        self.client.post(
            "/api/payments/fee-structures/grid/",
            {
                "term": 1, "year": 2026,
                "columns": ["Tuition", "Transport"],
                "rows": [{"grade": 5, "breakdown": {"Tuition": "9000", "Transport": "3000"}}],
            },
            format="json",
        )
        self.client.patch(
            "/api/my-school/profile/", {"vote_heads": ["Tuition"]}, format="json"
        )
        grid = self.client.get("/api/payments/fee-structures/grid/?term=1&year=2026")
        self.assertEqual(grid.data["columns"], ["Tuition", "Transport"])


class DocumentTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        self.teacher = make_teacher(self.school)

    def _upload(self, title="Registration certificate", category="REGISTRATION"):
        return self.client.post(
            "/api/school-documents/",
            {
                "title": title,
                "category": category,
                "file": SimpleUploadedFile("cert.pdf", b"%PDF-1.4 ...",
                                           content_type="application/pdf"),
            },
            format="multipart",
        )

    def test_the_office_files_a_document(self):
        self.client.force_authenticate(self.admin)
        res = self._upload()
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["category_label"], "Registration & licences")
        self.assertTrue(res.data["file_url"])
        self.assertEqual(
            SchoolDocument.objects.get().uploaded_by_id, self.admin.id
        )

    def test_staff_may_read_the_cabinet_but_not_file_in_it(self):
        self.client.force_authenticate(self.admin)
        self._upload()
        self.client.force_authenticate(self.teacher.user)
        listed = self.client.get("/api/school-documents/")
        self.assertEqual(listed.data["count"], 1)
        denied = self._upload("Mine", "POLICY")
        self.assertEqual(denied.status_code, 403)

    def test_one_school_never_sees_another_school_s_papers(self):
        self.client.force_authenticate(self.admin)
        self._upload()
        elsewhere = make_school("Elsewhere")
        self.client.force_authenticate(make_user(elsewhere, "ADMIN"))
        res = self.client.get("/api/school-documents/")
        self.assertEqual(res.data["count"], 0)


class LetterheadTests(APITestCase):
    """A crest is only worth uploading if it reaches the paper that goes home."""

    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")

    def test_the_report_card_carries_the_school_s_own_letterhead(self):
        from apps.assessments.reports import build_report_card
        from tests.factories import make_learner

        self.school.motto = "Education is light"
        self.school.contact_phone = "0722000111"
        self.school.postal_address = "P.O. Box 42, Nyeri"
        self.school.save()
        learner = make_learner(self.school, grade=5)
        data = build_report_card(learner, term=1, year=2026)
        self.assertEqual(data["school"]["motto"], "Education is light")
        self.assertEqual(data["school"]["phone"], "0722000111")
        self.assertEqual(data["school"]["address"], "P.O. Box 42, Nyeri")

    def test_both_office_numbers_appear_when_the_school_has_two(self):
        from apps.schools.profile import school_letterhead

        self.school.contact_phone = "0722000111"
        self.school.alt_phone = "0733000222"
        head = school_letterhead(self.school)
        self.assertEqual(head["phone"], "0722000111 / 0733000222")

    def test_the_report_card_still_prints_without_a_crest(self):
        from apps.assessments.pdf import render_report_card_pdf
        from apps.assessments.reports import build_report_card
        from tests.factories import make_learner

        learner = make_learner(self.school, grade=5)
        pdf = render_report_card_pdf(build_report_card(learner, term=1, year=2026))
        self.assertTrue(pdf.startswith(b"%PDF"))

    def test_the_crest_is_drawn_onto_the_report_card(self):
        from apps.assessments.pdf import render_report_card_pdf
        from apps.assessments.reports import build_report_card
        from tests.factories import make_learner

        self.client.force_authenticate(self.admin)
        self.client.patch("/api/my-school/profile/", {"logo": _png()}, format="multipart")
        self.school.refresh_from_db()
        learner = make_learner(self.school, grade=5)
        data = build_report_card(learner, term=1, year=2026)
        self.assertTrue(data["school"]["logo_path"])
        pdf = render_report_card_pdf(data)
        self.assertTrue(pdf.startswith(b"%PDF"))
