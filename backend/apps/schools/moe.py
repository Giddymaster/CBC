"""The Ministry of Education structure — the authority this system follows.

**Conflict rule:** where any other source disagrees with this module — a project
brief, a textbook, a school's own document, or a model's output — this module
wins. Everything that needs to know the shape of Kenyan basic education imports
it from here rather than restating it, so there is exactly one place to correct
when MoE changes something.

Two conflicts already resolved this way:

1. The founding brief named four Senior School pathways (STEM, Humanities,
   Arts & Sports, Social Sciences). MoE defines **three**. "Humanities" is not a
   pathway — it is a track inside Social Sciences, and it is modelled as one
   below. The brief's intent is preserved; the structure follows MoE.

2. The brief called the levels "Primary / JSS / Senior". MoE distinguishes
   Lower Primary from Upper Primary, and the register needs Pre-Primary and
   Play Group. The fuller MoE breakdown is used.

This module holds *structure* only — the parts that are stable and
well-established. Detailed curriculum content (strands, sub-strands, outcomes)
is not hard-coded here; it comes from the curriculum documents in
`apps.knowledge`, which carry their own citations.
"""

# --- Source authority ----------------------------------------------------
# Higher rank wins when two documents disagree. Used to order retrieval and to
# tell the reader which source governs.
AUTHORITY_RANK = {
    "MOE": 100,      # Ministry of Education — policy, circulars, structure
    "KICD": 90,      # Kenya Institute of Curriculum Development — designs, approved texts
    "KNEC": 85,      # Kenya National Examinations Council — assessment framework
    "TSC": 80,       # Teachers Service Commission — staffing, PD
    "COUNTY": 60,    # County education office
    "SCHOOL": 40,    # The school's own documents
    "OTHER": 10,     # Anything else — reference material, commentary
}

AUTHORITY_LABELS = {
    "MOE": "Ministry of Education",
    "KICD": "Kenya Institute of Curriculum Development",
    "KNEC": "Kenya National Examinations Council",
    "TSC": "Teachers Service Commission",
    "COUNTY": "County education office",
    "SCHOOL": "School document",
    "OTHER": "Other reference",
}

GOVERNING_AUTHORITY = "MOE"


def authority_rank(code):
    return AUTHORITY_RANK.get(code, 0)


def governs(a, b):
    """Which of two authority codes governs when they disagree."""
    return a if authority_rank(a) >= authority_rank(b) else b


# --- Levels and grades ---------------------------------------------------
# Grade numbers are the integers stored on Learner.grade.
LEVELS = [
    {"key": "PRE_PRIMARY", "name": "Pre-Primary", "grades": [-2, -1, 0]},
    {"key": "LOWER_PRIMARY", "name": "Lower Primary", "grades": [1, 2, 3]},
    {"key": "UPPER_PRIMARY", "name": "Upper Primary", "grades": [4, 5, 6]},
    {"key": "JUNIOR_SCHOOL", "name": "Junior School", "grades": [7, 8, 9]},
    {"key": "SENIOR_SCHOOL", "name": "Senior School", "grades": [10, 11, 12]},
]

GRADE_LABELS = {-2: "PG", -1: "PP1", 0: "PP2", **{g: f"Grade {g}" for g in range(1, 13)}}

ALL_GRADES = [g for level in LEVELS for g in level["grades"]]


def level_of(grade):
    for level in LEVELS:
        if grade in level["grades"]:
            return level
    return None


# --- Senior School pathways ---------------------------------------------
# Three pathways. Tracks are the specialisations within each — this is where
# "Humanities" lives.
PATHWAYS = [
    {
        "code": "STEM",
        "name": "STEM",
        "tracks": [
            "Pure Sciences",
            "Applied Sciences",
            "Technical and Engineering",
            "Career and Technology Studies",
        ],
    },
    {
        "code": "SOCIAL",
        "name": "Social Sciences",
        "tracks": [
            "Humanities and Business Studies",
            "Languages and Literature",
        ],
    },
    {
        "code": "ARTS_SPORTS",
        "name": "Arts and Sports Science",
        "tracks": ["Arts", "Sports Science"],
    },
]

PATHWAY_CODES = [p["code"] for p in PATHWAYS]


def pathway(code):
    return next((p for p in PATHWAYS if p["code"] == code), None)


def pathway_for_track(track):
    """Resolve a track name — including 'Humanities' — to its MoE pathway."""
    needle = (track or "").strip().lower()
    if not needle:
        return None
    for p in PATHWAYS:
        for t in p["tracks"]:
            if needle in t.lower():
                return p
    return None


# --- Learning areas by level ---------------------------------------------
# The KICD rationalised curriculum (2023) for basic education, and the
# gazetted Senior School subjects (compulsory four plus the common pathway
# subjects). One entry per distinct name; a name taught across levels carries
# the union of its grades. Schools trim or extend the list — this is the
# starting canon, not a cage.
LEARNING_AREAS = [
    # Pre-Primary (PP1–PP2); activity areas that continue into Lower Primary
    # keep one row spanning both levels.
    {"code": "LANGA", "name": "Language Activities", "grades": [-1, 0]},
    {"code": "MATHA", "name": "Mathematical Activities", "grades": [-1, 0, 1, 2, 3]},
    {"code": "ENVA", "name": "Environmental Activities", "grades": [-1, 0, 1, 2, 3]},
    {"code": "CREA", "name": "Creative Activities", "grades": [-1, 0, 1, 2, 3]},
    {"code": "RELA", "name": "Religious Education Activities", "grades": [-1, 0, 1, 2, 3]},
    # Lower Primary (G1–G3)
    {"code": "ENGA", "name": "English Language Activities", "grades": [1, 2, 3]},
    {"code": "KISA", "name": "Kiswahili Language Activities", "grades": [1, 2, 3]},
    {"code": "INDA", "name": "Indigenous Language Activities", "grades": [1, 2, 3]},
    # Upper Primary (G4–G6) → Junior School (G7–G9) → Senior School where
    # compulsory (English, Kiswahili) or offered as a pathway subject (Maths).
    {"code": "ENG", "name": "English", "grades": [4, 5, 6, 7, 8, 9, 10, 11, 12]},
    {"code": "KIS", "name": "Kiswahili", "grades": [4, 5, 6, 7, 8, 9, 10, 11, 12]},
    {"code": "MATH", "name": "Mathematics", "grades": [4, 5, 6, 7, 8, 9, 10, 11, 12]},
    {"code": "RE", "name": "Religious Education", "grades": [4, 5, 6, 7, 8, 9]},
    {"code": "SCITEC", "name": "Science and Technology", "grades": [4, 5, 6]},
    {"code": "SST", "name": "Social Studies", "grades": [4, 5, 6, 7, 8, 9]},
    {"code": "AGRN", "name": "Agriculture and Nutrition", "grades": [4, 5, 6, 7, 8, 9]},
    {"code": "CRARTS", "name": "Creative Arts", "grades": [4, 5, 6]},
    # Junior School (G7–G9)
    {"code": "INTSCI", "name": "Integrated Science", "grades": [7, 8, 9]},
    {"code": "PTS", "name": "Pre-Technical Studies", "grades": [7, 8, 9]},
    {"code": "CAS", "name": "Creative Arts and Sports", "grades": [7, 8, 9]},
    # Senior School (G10–G12): the other compulsory two…
    {"code": "CSL", "name": "Community Service Learning", "grades": [10, 11, 12]},
    {"code": "PE", "name": "Physical Education", "grades": [10, 11, 12]},
    # …and the common pathway subjects.
    {"code": "BIO", "name": "Biology", "grades": [10, 11, 12]},
    {"code": "CHEM", "name": "Chemistry", "grades": [10, 11, 12]},
    {"code": "PHY", "name": "Physics", "grades": [10, 11, 12]},
    {"code": "GSCI", "name": "General Science", "grades": [10, 11, 12]},
    {"code": "AGR", "name": "Agriculture", "grades": [10, 11, 12]},
    {"code": "COMP", "name": "Computer Studies", "grades": [10, 11, 12]},
    {"code": "HSCI", "name": "Home Science", "grades": [10, 11, 12]},
    {"code": "BST", "name": "Business Studies", "grades": [10, 11, 12]},
    {"code": "GEO", "name": "Geography", "grades": [10, 11, 12]},
    {"code": "HIST", "name": "History and Citizenship", "grades": [10, 11, 12]},
    {"code": "CRE", "name": "Christian Religious Education", "grades": [10, 11, 12]},
    {"code": "IRE", "name": "Islamic Religious Education", "grades": [10, 11, 12]},
    {"code": "HRE", "name": "Hindu Religious Education", "grades": [10, 11, 12]},
    {"code": "LIT", "name": "Literature in English", "grades": [10, 11, 12]},
    {"code": "FAS", "name": "Fasihi ya Kiswahili", "grades": [10, 11, 12]},
    {"code": "MUSD", "name": "Music and Dance", "grades": [10, 11, 12]},
    {"code": "FART", "name": "Fine Arts", "grades": [10, 11, 12]},
    {"code": "THF", "name": "Theatre and Film", "grades": [10, 11, 12]},
    {"code": "SPR", "name": "Sports and Recreation", "grades": [10, 11, 12]},
    {"code": "FRE", "name": "French", "grades": [10, 11, 12]},
    {"code": "GER", "name": "German", "grades": [10, 11, 12]},
    {"code": "ARB", "name": "Arabic", "grades": [10, 11, 12]},
    {"code": "MAN", "name": "Mandarin Chinese", "grades": [10, 11, 12]},
]


# --- Competency levels ---------------------------------------------------
COMPETENCY_LEVELS = [
    {"code": "EE", "name": "Exceeding Expectation"},
    {"code": "ME", "name": "Meeting Expectation"},
    {"code": "AE", "name": "Approaching Expectation"},
    {"code": "BE", "name": "Below Expectation"},
]


# --- Transition points ---------------------------------------------------
# The moments a learner moves between levels. `selects_pathway` marks the one
# transition that assigns a Senior School pathway.
TRANSITIONS = [
    {
        "key": "G6_TO_G7",
        "name": "Primary to Junior School",
        "from_grade": 6,
        "to_grade": 7,
        "selects_pathway": False,
        "note": "100% transition policy — every learner proceeds to Junior School.",
    },
    {
        "key": "G9_TO_G10",
        "name": "Junior to Senior School",
        "from_grade": 9,
        "to_grade": 10,
        "selects_pathway": True,
        "note": "Learners are placed on a Senior School pathway at this point.",
    },
    {
        "key": "G12_EXIT",
        "name": "Senior School exit",
        "from_grade": 12,
        "to_grade": None,
        "selects_pathway": False,
        "note": "Exit to tertiary education, training or work.",
    },
]


def transition_from(grade):
    return next((t for t in TRANSITIONS if t["from_grade"] == grade), None)


# Default subject-to-pathway affinity, used only to *propose* a Senior School
# pathway from a learner's Junior School record.
#
# This is a planning aid, not the national placement rule. MoE placement weighs
# KJSEA performance, the learner's own choice, and the capacity of the receiving
# school — none of which this system can decide. Every proposal it makes is
# advisory and must be confirmed by the head teacher before it takes effect.
#
# Matching is by substring against the learning area name, so a school that
# names a subject differently still matches.
PATHWAY_INDICATORS = {
    "STEM": [
        "mathematic", "integrated science", "science", "pre-technical",
        "pre technical", "computer", "agriculture", "health education",
    ],
    "SOCIAL": [
        "social studies", "business", "english", "kiswahili", "religious",
        "history", "geography", "language", "literature",
    ],
    "ARTS_SPORTS": [
        "creative art", "performing art", "sport", "music", "art and craft",
        "physical education", "drama",
    ],
}


def pathway_affinity(learning_area_name):
    """Which pathway a subject speaks to, or None if it says nothing useful."""
    needle = (learning_area_name or "").lower()
    for code, indicators in PATHWAY_INDICATORS.items():
        if any(indicator in needle for indicator in indicators):
            return code
    return None


def next_grade(grade):
    """The grade a learner moves to at the end of the year, or None at exit."""
    if grade >= 12:
        return None
    if grade not in ALL_GRADES:
        return None
    return grade + 1


def structure_summary():
    """The canon, in one payload, for the UI and for grounding prompts."""
    return {
        "governing_authority": GOVERNING_AUTHORITY,
        "authority_order": sorted(
            AUTHORITY_RANK, key=lambda c: -AUTHORITY_RANK[c]
        ),
        "levels": [
            {**level, "labels": [GRADE_LABELS[g] for g in level["grades"]]}
            for level in LEVELS
        ],
        "pathways": PATHWAYS,
        "competency_levels": COMPETENCY_LEVELS,
        "transitions": TRANSITIONS,
    }
