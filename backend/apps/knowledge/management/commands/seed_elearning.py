"""Stock the E-learning shelf with a national starter set.

A school should open the library to something, not an empty page. This seeds
NATIONAL resources (school = null, so every tenant sees them) pointing at real,
freely-available Kenyan CBC material — the Kenya Education Cloud (KICD's official
free digital-learning platform), KICD curriculum designs, KNEC, and curated
YouTube video-lesson searches per subject and level.

Idempotent and re-runnable: resources are matched by (title, url) so running it
again tops up new entries without duplicating old ones. Schools edit, hide or
add to this shelf from the E-Learning page; nothing here is locked.

    python manage.py seed_elearning

Deliberately institutional links rather than guessed single videos: a link to
the Kenya Education Cloud science shelf never rots the way one hard-coded video
id can, and it is where the current, vetted content actually lives.
"""

from django.core.management.base import BaseCommand

from apps.assessments.models import LearningArea
from apps.knowledge.models import LearningResource, Source

KEC = "https://kec.ac.ke"  # Kenya Education Cloud — KICD's free content platform


def yt(query):
    """A YouTube search that always resolves to current lessons for a topic."""
    from urllib.parse import quote_plus

    return f"https://www.youtube.com/results?search_query={quote_plus(query)}"


# (kind, title, url, description, area_code_or_None, grades)
RESOURCES = [
    # --- Platform-wide, for parents and any grade -----------------------
    ("LINK", "Kenya Education Cloud — free CBC content",
     KEC,
     "KICD's official platform: video lessons, notes and e-books for every grade and subject.",
     None, []),
    ("LINK", "KICD Curriculum Designs (all grades)",
     "https://kicd.ac.ke/curriculum-reforms/curriculum-designs/",
     "The official CBC designs — what each learning area covers, grade by grade.",
     None, []),
    ("PAPER", "KNEC — assessment and past papers",
     "https://www.knec.ac.ke/",
     "The national examinations council: assessment reports and past papers.",
     None, []),

    # --- Languages ------------------------------------------------------
    ("LINK", "English — video lessons (Grades 4-9)",
     yt("CBC English Kenya grade 7 lesson"),
     "Reading, grammar and composition lessons aligned to the CBC.",
     "ENG", [4, 5, 6, 7, 8, 9]),
    ("LINK", "Kiswahili — masomo ya video",
     yt("CBC Kiswahili Kenya darasa la 7"),
     "Masomo ya lugha, insha na fasihi kwa mtaala mpya.",
     "KIS", [4, 5, 6, 7, 8, 9]),

    # --- Mathematics ----------------------------------------------------
    ("LINK", "Mathematics — video lessons (Grades 4-9)",
     yt("CBC Mathematics Kenya grade 7"),
     "Numbers, algebra, geometry and measurement, worked step by step.",
     "MATH", [4, 5, 6, 7, 8, 9]),
    ("LINK", "Mathematics on Kenya Education Cloud",
     KEC,
     "Interactive maths lessons and practice, by grade.",
     "MATH", [4, 5, 6, 7, 8, 9]),

    # --- Science --------------------------------------------------------
    ("LINK", "Integrated Science — video lessons (JSS)",
     yt("CBC Integrated Science grade 7 Kenya"),
     "Living things, matter, energy and the environment for Junior School.",
     "INTSCI", [7, 8, 9]),
    ("LINK", "Science and Technology — Upper Primary",
     yt("CBC Science and Technology grade 5 Kenya"),
     "Video lessons on living things, energy, and simple machines.",
     "SCITEC", [4, 5, 6]),

    # --- Social Studies -------------------------------------------------
    ("LINK", "Social Studies — video lessons",
     yt("CBC Social Studies grade 7 Kenya"),
     "People, places, resources and citizenship across Kenya and Africa.",
     "SST", [4, 5, 6, 7, 8, 9]),

    # --- Agriculture & Nutrition ---------------------------------------
    ("LINK", "Agriculture and Nutrition — video lessons",
     yt("CBC Agriculture and Nutrition grade 7 Kenya"),
     "Crops, soil, livestock and food for Upper Primary and JSS.",
     "AGRN", [4, 5, 6, 7, 8, 9]),

    # --- Pre-Technical / Creative Arts ---------------------------------
    ("LINK", "Pre-Technical Studies — video lessons",
     yt("CBC Pre-Technical Studies grade 8 Kenya"),
     "Tools, materials, drawing and simple technology for JSS.",
     "PTS", [7, 8, 9]),
    ("LINK", "Creative Arts and Sports — video lessons",
     yt("CBC Creative Arts and Sports grade 7 Kenya"),
     "Art, music, and physical activity for Junior School.",
     "CAS", [7, 8, 9]),

    # --- Pre-Primary & Lower Primary (for parents) ---------------------
    ("LINK", "Pre-Primary activities on Kenya Education Cloud",
     KEC,
     "Language, number and creative activities for PP1 and PP2.",
     None, [-1, 0]),
]


class Command(BaseCommand):
    help = "Seed a national starter set of E-learning resources (idempotent)."

    def handle(self, *args, **options):
        kicd, _ = Source.objects.get_or_create(
            name="KICD", defaults={"authority": "KICD", "publisher": "Kenya Institute of Curriculum Development"}
        )
        area_by_code = {a.code: a for a in LearningArea.objects.all()}

        created = skipped = 0
        for kind, title, url, description, code, grades in RESOURCES:
            area = area_by_code.get(code) if code else None
            _, was_created = LearningResource.objects.get_or_create(
                title=title,
                url=url,
                defaults={
                    "kind": kind,
                    "description": description,
                    "learning_area": area,
                    "grades": grades,
                    "source": kicd,
                    "school": None,  # national — shared by every school
                },
            )
            created += was_created
            skipped += not was_created

        self.stdout.write(
            self.style.SUCCESS(
                f"E-learning shelf seeded: {created} added, {skipped} already present. "
                f"Total national resources now {LearningResource.objects.filter(school__isnull=True).count()}."
            )
        )
