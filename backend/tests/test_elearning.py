"""The e-learning library: YouTube parsing, RAG-ranked search, and who may curate."""

from rest_framework.test import APITestCase

from apps.knowledge.models import LearningResource, Source, youtube_id
from apps.knowledge.retrieval import search_resources
from tests.factories import make_learning_area, make_school, make_user


class YoutubeIdTests(APITestCase):
    def test_it_reads_every_shape_of_youtube_link(self):
        cases = {
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ": "dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ": "dQw4w9WgXcQ",
            "https://www.youtube.com/embed/dQw4w9WgXcQ": "dQw4w9WgXcQ",
            "https://www.youtube.com/shorts/dQw4w9WgXcQ": "dQw4w9WgXcQ",
            "dQw4w9WgXcQ": "dQw4w9WgXcQ",
        }
        for url, expected in cases.items():
            self.assertEqual(youtube_id(url), expected, url)

    def test_a_non_youtube_link_yields_nothing(self):
        self.assertEqual(youtube_id("https://example.com/video"), "")


class VisibilityTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.other = make_school("Other")
        self.maths = make_learning_area("Mathematics", "MATH")
        self.national = LearningResource.objects.create(
            kind="VIDEO", title="Fractions for Grade 7",
            url="https://youtu.be/dQw4w9WgXcQ", learning_area=self.maths, grades=[7],
        )
        self.mine = LearningResource.objects.create(
            school=self.school, kind="NOTES", title="Our revision pack",
            url="https://example.com/notes", learning_area=self.maths, grades=[7],
        )
        self.theirs = LearningResource.objects.create(
            school=self.other, kind="NOTES", title="Their pack",
            url="https://example.com/x", learning_area=self.maths,
        )
        self.admin = make_user(self.school, "ADMIN")

    def test_a_school_sees_national_and_its_own_not_another_schools(self):
        self.client.force_authenticate(self.admin)
        res = self.client.get("/api/learning-resources/")
        titles = {r["title"] for r in res.data["results"]}
        self.assertIn("Fractions for Grade 7", titles)
        self.assertIn("Our revision pack", titles)
        self.assertNotIn("Their pack", titles)

    def test_a_video_comes_back_ready_to_embed(self):
        self.client.force_authenticate(self.admin)
        res = self.client.get("/api/learning-resources/?kind=VIDEO")
        video = next(r for r in res.data["results"] if r["kind"] == "VIDEO")
        self.assertEqual(video["youtube_id"], "dQw4w9WgXcQ")
        self.assertEqual(video["youtube_embed"], "https://www.youtube.com/embed/dQw4w9WgXcQ")
        self.assertTrue(video["thumbnail"].endswith("dQw4w9WgXcQ/hqdefault.jpg"))

    def test_a_parent_may_browse_the_library(self):
        parent = make_user(self.school, "PARENT")
        self.client.force_authenticate(parent)
        res = self.client.get("/api/learning-resources/")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(len(res.data["results"]) >= 2)


class SearchTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.maths = make_learning_area("Mathematics", "MATH")
        self.science = make_learning_area("Science", "SCI")
        kicd = Source.objects.create(name="KICD", authority="KICD")
        LearningResource.objects.create(
            kind="VIDEO", title="Photosynthesis explained", topic="how plants make food",
            url="https://youtu.be/aaaaaaaaaaa", learning_area=self.science, grades=[7],
            source=kicd,
        )
        LearningResource.objects.create(
            kind="VIDEO", title="Adding fractions", topic="denominators",
            url="https://youtu.be/bbbbbbbbbbb", learning_area=self.maths, grades=[7],
        )

    def test_search_ranks_the_relevant_resource_first(self):
        results = search_resources("photosynthesis plants", school=self.school)
        self.assertTrue(results)
        self.assertEqual(results[0].title, "Photosynthesis explained")

    def test_an_empty_query_still_lists_the_shelf(self):
        results = search_resources("", school=self.school)
        self.assertEqual(len(results), 2)

    def test_a_grade_filter_narrows_the_shelf(self):
        results = search_resources("", school=self.school, grade=9)
        # grades=[7] means these do not cover grade 9
        self.assertEqual(results, [])


class CurationGuardTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        self.maths = make_learning_area("Mathematics", "MATH")

    def test_a_school_admin_adds_a_resource_to_their_own_school(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            "/api/learning-resources/",
            {"kind": "VIDEO", "title": "Intro to algebra",
             "url": "https://youtu.be/dQw4w9WgXcQ", "learning_area": self.maths.id,
             "grades": [7]},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(LearningResource.objects.get().school_id, self.school.id)

    def test_a_school_admin_cannot_publish_a_national_resource(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            "/api/learning-resources/",
            {"kind": "VIDEO", "title": "National", "school": None,
             "url": "https://youtu.be/dQw4w9WgXcQ"},
            format="json",
        )
        self.assertEqual(res.status_code, 403)

    def test_a_teacher_cannot_curate(self):
        teacher = make_user(self.school, "TEACHER")
        self.client.force_authenticate(teacher)
        res = self.client.post(
            "/api/learning-resources/",
            {"kind": "LINK", "title": "x", "url": "https://example.com"},
            format="json",
        )
        self.assertEqual(res.status_code, 403)

    def test_a_video_needs_a_real_youtube_link(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            "/api/learning-resources/",
            {"kind": "VIDEO", "title": "x", "url": "https://example.com/notyoutube"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_a_resource_needs_a_link_or_a_file(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            "/api/learning-resources/",
            {"kind": "NOTES", "title": "Empty"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
