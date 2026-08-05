"""The curriculum knowledge base: chunking, retrieval, tenancy, and the rule
that MoE structure governs when sources disagree."""

from rest_framework.test import APITestCase

from apps.knowledge.ingest import chunk_text, index_document, split_sections
from apps.knowledge.models import Chunk, Document, Source
from apps.knowledge.retrieval import authority_spread, build_context, search, tokenize
from apps.schools import moe
from apps.teachers.services.ai_scheme import retrieve_grounding
from tests.factories import make_learning_area, make_school, make_teacher, make_user

MOE_TEXT = """
GRADE 7 INTEGRATED SCIENCE

STRAND 1.0 SCIENTIFIC INVESTIGATION
Learners explore the laboratory, its apparatus and safety rules. The sub-strand
covers laboratory safety, common apparatus and their uses.

STRAND 2.0 MIXTURES ELEMENTS AND COMPOUNDS
Learners classify matter into mixtures, elements and compounds, and separate
mixtures using filtration, evaporation and chromatography.
"""

SCHOOL_TEXT = """
INTEGRATED SCIENCE DEPARTMENT NOTES

Mixtures elements and compounds
Our school teaches separation of mixtures in term two using only filtration,
because the laboratory has no chromatography paper.
"""


def make_source(authority="MOE", name=None):
    return Source.objects.create(
        name=name or f"{authority} source", authority=authority
    )


def make_document(*, school=None, authority="MOE", text=MOE_TEXT, title=None,
                  learning_area=None, grades=None, kind="DESIGN"):
    document = Document.objects.create(
        school=school,
        source=make_source(authority),
        title=title or f"{authority} document",
        kind=kind,
        learning_area=learning_area,
        grades=grades if grades is not None else [7],
        text=text,
    )
    index_document(document)
    return document


class ChunkingTests(APITestCase):
    def test_sections_follow_the_documents_own_headings(self):
        sections = split_sections(MOE_TEXT)
        headings = [h for h, _ in sections]
        self.assertIn("STRAND 1.0 SCIENTIFIC INVESTIGATION", headings)
        self.assertIn("STRAND 2.0 MIXTURES ELEMENTS AND COMPOUNDS", headings)

    def test_a_chunk_carries_its_heading_so_the_citation_is_useful(self):
        document = make_document()
        chunk = document.chunks.filter(heading__icontains="MIXTURES").first()
        self.assertIsNotNone(chunk)
        self.assertIn("MIXTURES", chunk.citation())
        self.assertIn(document.title, chunk.citation())

    def test_text_without_headings_still_indexes(self):
        chunks = chunk_text("Just one flat paragraph with no headings at all.")
        self.assertEqual(len(chunks), 1)

    def test_reindexing_replaces_rather_than_duplicates(self):
        document = make_document()
        first = document.chunks.count()
        index_document(document)
        self.assertEqual(document.chunks.count(), first)

    def test_a_heading_is_searchable(self):
        """'Sub-strand 2.1 Mixtures' is what a teacher types, and it lives only
        in the heading."""
        school = make_school()
        make_document(school=None, text="STRAND 2.0 MIXTURES ELEMENTS AND COMPOUNDS\n"
                                        "Learners classify matter and separate it.")
        results = search("mixtures elements compounds", school=school)
        self.assertTrue(results)

    def test_stopwords_are_dropped(self):
        self.assertNotIn("the", tokenize("the laboratory and the apparatus"))
        self.assertIn("laboratory", tokenize("the laboratory and the apparatus"))


class RetrievalTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.science = make_learning_area("Integrated Science", "SCI")

    def test_a_query_finds_the_relevant_passage(self):
        make_document(learning_area=self.science)
        results = search("separating mixtures by filtration", school=self.school)
        self.assertTrue(results)
        self.assertIn("filtration", results[0].text.lower())

    def test_a_query_repeating_a_word_still_matches(self):
        """'strand sub-strand' repeats 'strand'. Counting it once per chunk per
        occurrence pushed the document frequency above the corpus size, which
        made the IDF negative and silently dropped every result."""
        make_document(learning_area=self.science)
        self.assertTrue(search("strand sub-strand", school=self.school))

    def test_a_term_in_every_passage_never_subtracts(self):
        make_document(learning_area=self.science)
        common = search("learners", school=self.school)  # appears in every chunk
        for passage in common:
            self.assertGreater(passage.score, 0)

    def test_an_empty_library_returns_nothing_rather_than_failing(self):
        self.assertEqual(search("anything at all", school=self.school), [])

    def test_a_query_of_only_stopwords_returns_nothing(self):
        make_document()
        self.assertEqual(search("the and of", school=self.school), [])

    def test_grade_filter_excludes_other_grades(self):
        make_document(grades=[7], learning_area=self.science)
        self.assertTrue(search("mixtures", school=self.school, grade=7))
        self.assertEqual(search("mixtures", school=self.school, grade=10), [])

    def test_a_document_with_no_grades_applies_everywhere(self):
        make_document(grades=[])
        self.assertTrue(search("mixtures", school=self.school, grade=11))

    def test_a_subject_filter_keeps_general_documents(self):
        make_document(learning_area=None, title="General policy")
        results = search("mixtures", school=self.school, learning_area=self.science.id)
        self.assertTrue(results)


class TenancyTests(APITestCase):
    def setUp(self):
        self.mine = make_school("Mine")
        self.theirs = make_school("Theirs")
        self.science = make_learning_area("Integrated Science", "SCI")

    def test_national_documents_are_shared(self):
        make_document(school=None, title="KICD design")
        titles = [p.document_title for p in search("mixtures", school=self.mine)]
        self.assertIn("KICD design", titles)

    def test_another_schools_document_is_never_retrieved(self):
        make_document(school=self.theirs, authority="SCHOOL",
                      text=SCHOOL_TEXT, title="Their private notes")
        titles = [p.document_title for p in search("mixtures", school=self.mine)]
        self.assertNotIn("Their private notes", titles)

    def test_my_own_document_is_retrieved(self):
        make_document(school=self.mine, authority="SCHOOL",
                      text=SCHOOL_TEXT, title="My notes")
        titles = [p.document_title for p in search("mixtures", school=self.mine)]
        self.assertIn("My notes", titles)

    def test_the_document_api_hides_other_tenants(self):
        make_document(school=self.theirs, title="Theirs")
        make_document(school=self.mine, title="Mine")
        make_document(school=None, title="National")
        self.client.force_authenticate(make_user(self.mine, "ADMIN"))
        res = self.client.get("/api/curriculum/documents/")
        titles = [d["title"] for d in res.data["results"]]
        self.assertCountEqual(titles, ["Mine", "National"])


class AuthorityTests(APITestCase):
    """The conflict rule: MoE governs."""

    def setUp(self):
        self.school = make_school()
        self.science = make_learning_area("Integrated Science", "SCI")

    def test_moe_outranks_kicd_outranks_school(self):
        self.assertGreater(moe.authority_rank("MOE"), moe.authority_rank("KICD"))
        self.assertGreater(moe.authority_rank("KICD"), moe.authority_rank("SCHOOL"))
        self.assertEqual(moe.governs("SCHOOL", "MOE"), "MOE")
        self.assertEqual(moe.governs("MOE", "KICD"), "MOE")

    def test_the_higher_authority_leads_when_both_match(self):
        make_document(school=self.school, authority="SCHOOL",
                      text=SCHOOL_TEXT, title="School notes")
        make_document(school=None, authority="MOE",
                      text=MOE_TEXT, title="MoE circular")
        results = search("mixtures elements and compounds", school=self.school)
        self.assertEqual(results[0].authority, "MOE")

    def test_the_spread_names_the_governing_authority(self):
        make_document(school=self.school, authority="SCHOOL", text=SCHOOL_TEXT)
        make_document(school=None, authority="MOE", text=MOE_TEXT)
        spread = authority_spread(search("mixtures", school=self.school))
        self.assertTrue(spread["mixed"])
        self.assertEqual(spread["governing"], "MOE")

    def test_a_single_authority_is_not_reported_as_mixed(self):
        make_document(school=None, authority="MOE", text=MOE_TEXT)
        spread = authority_spread(search("mixtures", school=self.school))
        self.assertFalse(spread["mixed"])
        self.assertEqual(spread["governing"], "MOE")

    def test_context_presents_the_governing_source_first(self):
        make_document(school=self.school, authority="SCHOOL",
                      text=SCHOOL_TEXT, title="School notes")
        make_document(school=None, authority="MOE",
                      text=MOE_TEXT, title="MoE circular")
        context = build_context(search("mixtures", school=self.school))
        self.assertLess(context.index("MoE circular"), context.index("School notes"))

    def test_authority_does_not_override_a_clearly_better_match(self):
        """A vaguely-relevant MoE passage must not displace a precise one."""
        make_document(school=None, authority="MOE", text=MOE_TEXT,
                      title="MoE general science")
        make_document(school=self.school, authority="SCHOOL", grades=[7],
                      title="School chromatography guide",
                      text="CHROMATOGRAPHY\nChromatography paper strips separate "
                           "ink pigments. Chromatography chromatography technique.")
        results = search("chromatography paper strips", school=self.school)
        self.assertEqual(results[0].document_title, "School chromatography guide")


class SearchApiTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        self.science = make_learning_area("Integrated Science", "SCI")
        make_document(school=None, authority="MOE", learning_area=self.science)
        self.client.force_authenticate(self.admin)

    def test_search_returns_cited_results(self):
        res = self.client.get("/api/curriculum/search/?q=mixtures")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["results"])
        first = res.data["results"][0]
        self.assertIn("citation", first)
        self.assertIn("Ministry of Education", first["citation"])

    def test_search_requires_a_query(self):
        self.assertEqual(self.client.get("/api/curriculum/search/").status_code, 400)

    def test_a_junk_grade_is_a_400_not_a_500(self):
        res = self.client.get("/api/curriculum/search/?q=mixtures&grade=abc")
        self.assertEqual(res.status_code, 400)

    def test_search_needs_authentication(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/curriculum/search/?q=x").status_code, 401)


class DocumentWriteTests(APITestCase):
    def setUp(self):
        self.school = make_school()
        self.admin = make_user(self.school, "ADMIN")
        self.teacher = make_teacher(self.school)
        self.source = make_source("SCHOOL")

    def _payload(self, **extra):
        return {
            "source": self.source.id,
            "title": "Our science notes",
            "kind": "GUIDE",
            "text": SCHOOL_TEXT,
            "grades": [7],
            **extra,
        }

    def test_admin_upload_is_indexed_immediately(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post("/api/curriculum/documents/", self._payload(), format="json")
        self.assertEqual(res.status_code, 201, res.data)
        document = Document.objects.get(pk=res.data["id"])
        self.assertEqual(document.school_id, self.school.id)
        self.assertIsNotNone(document.indexed_at)
        self.assertTrue(document.chunks.exists())

    def test_a_teacher_cannot_add_to_the_library(self):
        self.client.force_authenticate(self.teacher.user)
        res = self.client.post("/api/curriculum/documents/", self._payload(), format="json")
        self.assertEqual(res.status_code, 403)

    def test_a_school_admin_cannot_publish_a_national_document(self):
        """A national document reaches every tenant, so it is not theirs to add."""
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            "/api/curriculum/documents/", self._payload(school=None), format="json"
        )
        self.assertEqual(res.status_code, 403)
        self.assertFalse(Document.objects.filter(school__isnull=True).exists())

    def test_a_school_admin_cannot_write_into_another_school(self):
        elsewhere = make_school("Elsewhere")
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            "/api/curriculum/documents/", self._payload(school=elsewhere.id), format="json"
        )
        self.assertEqual(res.status_code, 403)

    def test_a_platform_superuser_can_publish_a_national_document(self):
        superuser = make_user(self.school, "ADMIN", username="platform")
        superuser.is_superuser = True
        superuser.save()
        self.client.force_authenticate(superuser)
        res = self.client.post(
            "/api/curriculum/documents/", self._payload(school=None), format="json"
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertTrue(Document.objects.get(pk=res.data["id"]).is_national)

    def test_editing_the_text_reindexes(self):
        self.client.force_authenticate(self.admin)
        created = self.client.post(
            "/api/curriculum/documents/", self._payload(), format="json"
        )
        document_id = created.data["id"]
        self.client.patch(
            f"/api/curriculum/documents/{document_id}/",
            {"text": "FILTRATION\nOnly filtration is taught here."},
            format="json",
        )
        chunks = Chunk.objects.filter(document_id=document_id)
        self.assertTrue(any("filtration" in c.text.lower() for c in chunks))
        self.assertFalse(any("chromatography" in c.text.lower() for c in chunks))


class GroundingTests(APITestCase):
    """What the scheme generator is handed, and what the reviewer is told."""

    def setUp(self):
        self.school = make_school()
        self.science = make_learning_area("Integrated Science", "SCI")

    def test_grounding_is_empty_when_the_library_is(self):
        grounding = retrieve_grounding(
            learning_area_name="Integrated Science", learning_area_id=self.science.id,
            grade=7, term=1, school=self.school,
        )
        self.assertEqual(grounding["passages"], [])
        self.assertEqual(grounding["context"], "")

    def test_grounding_finds_the_curriculum_design(self):
        make_document(school=None, authority="KICD",
                      learning_area=self.science, grades=[7])
        grounding = retrieve_grounding(
            learning_area_name="Integrated Science", learning_area_id=self.science.id,
            grade=7, term=1, school=self.school,
        )
        self.assertTrue(grounding["passages"])
        self.assertIn("STRAND", grounding["context"])
        self.assertEqual(grounding["authority"]["governing"], "KICD")

    def test_a_policy_circular_does_not_ground_a_scheme_of_work(self):
        """A structural document mentioning Grade 7 must not be mistaken for
        Grade 7 curriculum content."""
        make_document(school=None, authority="MOE", kind="POLICY", grades=[7],
                      title="Transition policy",
                      text="TRANSITION\nGrade 7 learners proceed from primary. "
                           "Grade 7 strand assessment learning outcomes.")
        grounding = retrieve_grounding(
            learning_area_name="Integrated Science", learning_area_id=self.science.id,
            grade=7, term=1, school=self.school,
        )
        titles = [p.document_title for p in grounding["passages"]]
        self.assertNotIn("Transition policy", titles)

    def test_an_ungrounded_scheme_says_so(self):
        from apps.teachers.services.ai_scheme import generate_scheme

        scheme = generate_scheme(
            learning_area="Integrated Science", learning_area_id=self.science.id,
            school=self.school, grade=7, term=1, year=2026, weeks=2,
        )
        self.assertFalse(scheme["grounding"]["grounded"])
        self.assertIn("No curriculum documents matched", scheme["grounding"]["note"])

    def test_a_grounded_scheme_carries_its_sources(self):
        from apps.teachers.services.ai_scheme import generate_scheme

        make_document(school=None, authority="MOE",
                      learning_area=self.science, grades=[7])
        scheme = generate_scheme(
            learning_area="Integrated Science", learning_area_id=self.science.id,
            school=self.school, grade=7, term=1, year=2026, weeks=2,
        )
        self.assertTrue(scheme["grounding"]["grounded"])
        self.assertTrue(scheme["grounding"]["sources"])
        self.assertIn("Ministry of Education", scheme["grounding"]["note"])
        # The stub seeds strands from real headings rather than placeholders.
        strands = [l["strand"] for w in scheme["weeks"] for l in w["lessons"]]
        self.assertTrue(any("STRAND" in s for s in strands))

    def test_mixed_authorities_are_flagged_for_the_reviewer(self):
        from apps.teachers.services.ai_scheme import generate_scheme

        make_document(school=None, authority="MOE",
                      learning_area=self.science, grades=[7])
        # The school's own scheme guidance for the same subject and grade —
        # curriculum content, so it grounds a scheme alongside the national design.
        make_document(
            school=self.school, authority="SCHOOL", kind="GUIDE",
            learning_area=self.science, grades=[7],
            title="Our Grade 7 science plan",
            text=(
                "STRAND 2.0 MIXTURES ELEMENTS AND COMPOUNDS\n"
                "Learning outcomes for this strand are covered using filtration and "
                "evaporation only, because the laboratory has no chromatography paper. "
                "Key inquiry question and assessment follow the design."
            ),
        )
        scheme = generate_scheme(
            learning_area="Integrated Science", learning_area_id=self.science.id,
            school=self.school, grade=7, term=1, year=2026, weeks=1,
        )
        self.assertIn("Ministry of Education governs", scheme["grounding"]["note"])


class MoeCanonTests(APITestCase):
    """The structure that settles conflicts — including the brief's four pathways."""

    def test_moe_defines_three_pathways_not_four(self):
        self.assertEqual(len(moe.PATHWAYS), 3)
        self.assertCountEqual(moe.PATHWAY_CODES, ["STEM", "SOCIAL", "ARTS_SPORTS"])

    def test_humanities_resolves_to_the_social_sciences_pathway(self):
        """The brief listed Humanities as a pathway; MoE makes it a track."""
        resolved = moe.pathway_for_track("Humanities")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved["code"], "SOCIAL")

    def test_every_pathway_has_tracks(self):
        for pathway in moe.PATHWAYS:
            self.assertTrue(pathway["tracks"], pathway["code"])

    def test_levels_cover_play_group_to_grade_twelve(self):
        self.assertEqual(moe.ALL_GRADES, [-2, -1, 0] + list(range(1, 13)))
        self.assertEqual(moe.level_of(-2)["key"], "PRE_PRIMARY")
        self.assertEqual(moe.level_of(5)["key"], "UPPER_PRIMARY")
        self.assertEqual(moe.level_of(8)["key"], "JUNIOR_SCHOOL")
        self.assertEqual(moe.level_of(11)["key"], "SENIOR_SCHOOL")

    def test_the_pathway_is_selected_at_grade_nine(self):
        selecting = [t for t in moe.TRANSITIONS if t["selects_pathway"]]
        self.assertEqual(len(selecting), 1)
        self.assertEqual(selecting[0]["from_grade"], 9)

    def test_progression_stops_after_grade_twelve(self):
        self.assertEqual(moe.next_grade(6), 7)
        self.assertEqual(moe.next_grade(-2), -1)
        self.assertIsNone(moe.next_grade(12))

    def test_learner_pathway_choices_match_the_canon(self):
        from apps.students.models import Pathway

        self.assertCountEqual(
            [code for code, _ in Pathway.Code.choices], moe.PATHWAY_CODES
        )

    def test_competency_levels_match_the_assessment_engine(self):
        from apps.assessments.models import CompetencyLevel

        self.assertCountEqual(
            [c["code"] for c in moe.COMPETENCY_LEVELS],
            [code for code, _ in CompetencyLevel.choices],
        )

    def test_the_structure_endpoint_publishes_the_canon(self):
        school = make_school()
        self.client.force_authenticate(make_user(school, "TEACHER"))
        res = self.client.get("/api/moe/structure/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["governing_authority"], "MOE")
        self.assertEqual(res.data["authority_order"][0], "MOE")
        self.assertEqual(len(res.data["pathways"]), 3)
