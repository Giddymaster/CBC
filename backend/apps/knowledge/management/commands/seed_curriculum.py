"""Seed the curriculum library with enough to demonstrate grounded retrieval.

These are short, clearly-labelled *illustrative* extracts written for the demo —
not the real KICD designs, which a school must obtain and upload itself. The
titles say so, so nobody mistakes a demo fixture for the curriculum.
"""

from django.core.management.base import BaseCommand

from apps.assessments.models import LearningArea
from apps.knowledge.ingest import index_document
from apps.knowledge.models import Document, Source
from apps.schools.models import School

MOE_STRUCTURE = """
BASIC EDUCATION STRUCTURE

LEVELS OF BASIC EDUCATION
Basic education is organised as Pre-Primary (PP1 and PP2), Lower Primary
(Grade 1 to Grade 3), Upper Primary (Grade 4 to Grade 6), Junior School
(Grade 7 to Grade 9) and Senior School (Grade 10 to Grade 12).

SENIOR SCHOOL PATHWAYS
Senior School is organised into three pathways: Science, Technology,
Engineering and Mathematics; Social Sciences; and Arts and Sports Science.
Each pathway contains tracks. Humanities and Business Studies is a track within
the Social Sciences pathway, not a pathway in its own right. Languages and
Literature is also a track within Social Sciences.

TRANSITION
Transition from Grade 6 to Grade 7 is universal. Learners are placed on a
Senior School pathway at the end of Grade 9, taking account of performance,
interest and the capacity of the receiving school.

REPORTING OF ACHIEVEMENT
Learner achievement is reported against four performance levels: Exceeding
Expectation, Meeting Expectation, Approaching Expectation and Below
Expectation.
"""

SCIENCE_DESIGN = """
GRADE 7 INTEGRATED SCIENCE

STRAND 1.0 SCIENTIFIC INVESTIGATION
Sub-strand 1.1 Introduction to Integrated Science
By the end of the sub-strand the learner should be able to identify common
laboratory apparatus and state their uses, observe laboratory safety rules, and
appreciate the role of science in day to day life.
Key inquiry question: Why is it important to observe safety in the laboratory?
Learning experiences: learners tour the laboratory, identify apparatus in
groups, and draw up a class safety charter.
Assessment: observation, oral questions, practical checklist.

STRAND 2.0 MIXTURES ELEMENTS AND COMPOUNDS
Sub-strand 2.1 Mixtures
By the end of the sub-strand the learner should be able to classify matter as
mixtures, elements or compounds, separate mixtures using filtration,
evaporation, decantation and chromatography, and appreciate the application of
separation techniques in the community.
Key inquiry question: How do we separate the components of a mixture?
Learning experiences: learners separate a sand and salt mixture, use paper
chromatography to separate ink pigments, and relate the methods to water
treatment in the locality.
Assessment: practical work, written exercise, project.

STRAND 3.0 LIVING THINGS AND THEIR ENVIRONMENT
Sub-strand 3.1 The Cell
By the end of the sub-strand the learner should be able to describe the
structure of plant and animal cells, prepare and observe simple slides using a
light microscope, and appreciate the cell as the basic unit of life.
Key inquiry question: What makes up a living thing?
Learning experiences: learners prepare onion epidermis slides and observe them
under a microscope.
Assessment: practical work, drawings, oral questions.
"""

MATHS_DESIGN = """
GRADE 7 MATHEMATICS

STRAND 1.0 NUMBERS
Sub-strand 1.1 Whole Numbers
By the end of the sub-strand the learner should be able to read and write
numbers in symbols and words up to hundreds of millions, round off numbers to
the nearest given place value, and apply whole numbers in real life situations.
Key inquiry question: How do we use large numbers in daily life?
Learning experiences: learners read population figures from a newspaper and
round them off in groups.
Assessment: written exercise, oral questions.

STRAND 2.0 ALGEBRA
Sub-strand 2.1 Algebraic Expressions
By the end of the sub-strand the learner should be able to form algebraic
expressions from real life situations, simplify expressions by collecting like
terms, and appreciate the use of algebra in problem solving.
Key inquiry question: How can we represent an unknown quantity?
Learning experiences: learners model shopping problems using letters for
unknown prices.
Assessment: written exercise, group presentation.
"""

ASSESSMENT_FRAMEWORK = """
SCHOOL BASED ASSESSMENT

PURPOSE
School based assessment is continuous and formative. It informs teaching rather
than only ranking learners, and it contributes to the record of a learner's
competency development across the year.

PERFORMANCE LEVELS
Achievement is reported at four levels. Exceeding Expectation describes a
learner who applies the competency in new situations without support. Meeting
Expectation describes a learner who demonstrates the competency as set out in
the curriculum design. Approaching Expectation describes a learner who
demonstrates the competency with support. Below Expectation describes a learner
who has not yet demonstrated the competency and needs sustained intervention.

METHODS
Appropriate methods include observation schedules, oral questioning, written
tests, practical work, projects, portfolios and learner self-assessment. More
than one method should inform any judgement about a learner's level.
"""


class Command(BaseCommand):
    help = "Seed illustrative curriculum documents into the knowledge base"

    def handle(self, *args, **options):
        moe, _ = Source.objects.get_or_create(
            name="Ministry of Education — Basic Education Framework",
            defaults={"authority": "MOE", "publisher": "Ministry of Education, Kenya"},
        )
        kicd, _ = Source.objects.get_or_create(
            name="KICD Curriculum Designs",
            defaults={
                "authority": "KICD",
                "publisher": "Kenya Institute of Curriculum Development",
            },
        )
        knec, _ = Source.objects.get_or_create(
            name="KNEC Assessment Framework",
            defaults={
                "authority": "KNEC",
                "publisher": "Kenya National Examinations Council",
            },
        )

        science = LearningArea.objects.filter(name__icontains="science").first()
        maths = LearningArea.objects.filter(
            name__in=["Mathematics", "Maths"]
        ).first() or LearningArea.objects.filter(name__icontains="math").first()

        planned = [
            (moe, "Basic education structure and pathways (demo extract)",
             "POLICY", None, [], MOE_STRUCTURE),
            (kicd, "Grade 7 Integrated Science curriculum design (demo extract)",
             "DESIGN", science, [7], SCIENCE_DESIGN),
            (kicd, "Grade 7 Mathematics curriculum design (demo extract)",
             "DESIGN", maths, [7], MATHS_DESIGN),
            (knec, "School based assessment framework (demo extract)",
             "POLICY", None, [], ASSESSMENT_FRAMEWORK),
        ]

        created = 0
        for source, title, kind, area, grades, text in planned:
            document, made = Document.objects.get_or_create(
                title=title,
                school=None,  # national — shared by every school
                defaults={
                    "source": source,
                    "kind": kind,
                    "learning_area": area,
                    "grades": grades,
                    "text": text,
                },
            )
            if not made:
                document.text = text
                document.save(update_fields=["text", "updated_at"])
            chunks = index_document(document)
            created += made
            self.stdout.write(
                f"  {'+' if made else '~'} {title} -> {chunks} passages "
                f"[{source.authority}]"
            )

        # One school-level document, so the authority conflict is demonstrable.
        school = School.objects.first()
        if school:
            school_source, _ = Source.objects.get_or_create(
                name=f"{school.name} — department notes",
                defaults={"authority": "SCHOOL", "publisher": school.name},
            )
            doc, _ = Document.objects.get_or_create(
                title="Science department notes",
                school=school,
                defaults={
                    "source": school_source,
                    "kind": "GUIDE",
                    "learning_area": science,
                    "grades": [7],
                    "text": (
                        "SEPARATION OF MIXTURES\n"
                        "In this school we teach separation of mixtures in Term 2 using "
                        "filtration and evaporation only, because the laboratory has no "
                        "chromatography paper. Order paper before Term 2 if possible."
                    ),
                },
            )
            index_document(doc)
            self.stdout.write(f"  ~ {doc.title} [SCHOOL, {school.name}]")

        self.stdout.write(
            self.style.SUCCESS(
                f"Curriculum library seeded ({Document.objects.count()} documents, "
                f"{sum(d.chunks.count() for d in Document.objects.all())} passages)."
            )
        )
