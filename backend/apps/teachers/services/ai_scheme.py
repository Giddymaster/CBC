"""Scheme-of-work generation, grounded in the curriculum knowledge base.

Retrieval-augmented: before generating, the relevant passages from the school's
curriculum library are fetched and passed as context, and the model is required
to work from them and cite them. Without documents this falls back to ungrounded
generation and says so in the output, so a head teacher reviewing the scheme can
see whether it was written from the curriculum design or from the model's own
recollection.

**Conflict rule:** where retrieved sources disagree, the higher authority
governs — MoE above KICD above a school's own handout. The precedence is defined
once in `apps.schools.moe` and is stated to the model explicitly.
"""

import json
import os

from apps.schools.moe import (
    AUTHORITY_LABELS,
    GOVERNING_AUTHORITY,
    level_of,
)

SCHEME_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "weeks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "week": {"type": "integer"},
                    "lessons": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "lesson": {"type": "integer"},
                                "strand": {"type": "string"},
                                "sub_strand": {"type": "string"},
                                "learning_outcomes": {
                                    "type": "array", "items": {"type": "string"}
                                },
                                "learning_experiences": {"type": "string"},
                                "key_inquiry_question": {"type": "string"},
                                "resources": {"type": "string"},
                                "assessment_methods": {"type": "string"},
                                "sources": {
                                    "type": "array",
                                    "items": {"type": "integer"},
                                    "description": (
                                        "Numbers of the context passages this lesson "
                                        "was drawn from. Empty if none applied."
                                    ),
                                },
                            },
                            "required": [
                                "lesson", "strand", "sub_strand", "learning_outcomes",
                                "learning_experiences", "key_inquiry_question",
                                "resources", "assessment_methods", "sources",
                            ],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["week", "lessons"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["weeks"],
    "additionalProperties": False,
}


def _ai_configured() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


# A scheme of work is built from curriculum content, not from policy circulars.
# Restricting the grounding to these kinds keeps a structural document about
# transitions out of a Grade 7 science plan just because both mention "Grade 7".
SCHEME_SOURCE_KINDS = ["DESIGN", "GUIDE", "TEXTBOOK"]


def retrieve_grounding(*, learning_area_name, learning_area_id, grade, term, school):
    """Curriculum passages for this subject and grade, authority-ordered."""
    from apps.knowledge.retrieval import authority_spread, build_context, search

    query = " ".join(
        filter(
            None,
            [
                learning_area_name,
                f"grade {grade}",
                (
                    "strand sub-strand learning outcomes key inquiry question "
                    "learning experiences assessment"
                ),
            ],
        )
    )
    passages = search(
        query,
        school=school,
        learning_area=learning_area_id,
        grade=grade,
        kinds=SCHEME_SOURCE_KINDS,
        limit=10,
    )
    return {
        "passages": passages,
        "context": build_context(passages),
        "authority": authority_spread(passages),
    }


def _stub_scheme(learning_area, grade, weeks, lessons_per_week, grounding=None):
    """Deterministic KICD-shaped template for offline/dev use.

    When the library has passages, their headings seed the strands so the stub
    reflects the school's actual curriculum documents rather than placeholders.
    """
    passages = (grounding or {}).get("passages") or []
    headings = [p.heading for p in passages if p.heading]

    def strand_for(week):
        if headings:
            return headings[(week - 1) % len(headings)]
        return f"{learning_area} strand (week {week})"

    return {
        "weeks": [
            {
                "week": week,
                "lessons": [
                    {
                        "lesson": lesson,
                        "strand": strand_for(week),
                        "sub_strand": f"Sub-strand {week}.{lesson}",
                        "learning_outcomes": [
                            (
                                "By the end of the lesson the learner should be able to "
                                f"demonstrate competency {week}.{lesson} in {learning_area}."
                            )
                        ],
                        "learning_experiences": (
                            "Learners discuss, practise and present in groups."
                        ),
                        "key_inquiry_question": (
                            f"How do we apply {learning_area} concepts from week {week}?"
                        ),
                        "resources": "MoE-approved course book, charts, digital devices",
                        "assessment_methods": "Observation, oral questions, written exercise",
                        "sources": [],
                    }
                    for lesson in range(1, lessons_per_week + 1)
                ],
            }
            for week in range(1, weeks + 1)
        ],
        "generator": "template-stub (no ANTHROPIC_API_KEY configured)",
    }


def _grounding_note(grounding):
    """What the reviewer is told about where this scheme came from."""
    passages = grounding.get("passages") or []
    if not passages:
        return {
            "grounded": False,
            "note": (
                "No curriculum documents matched this subject and grade, so this "
                "scheme was written without them. Upload the KICD curriculum design "
                "to the curriculum library and regenerate for a grounded plan."
            ),
            "sources": [],
            "authority": grounding.get("authority", {}),
        }

    spread = grounding.get("authority", {})
    note = (
        f"Grounded in {len(passages)} passage(s) from the curriculum library. "
        f"Governing authority: {spread.get('governing_label', 'unknown')}."
    )
    if spread.get("mixed"):
        note += (
            " Sources of differing standing matched this query — where they "
            f"disagree, {AUTHORITY_LABELS[GOVERNING_AUTHORITY]} governs. Worth a look "
            "during review."
        )
    return {
        "grounded": True,
        "note": note,
        "sources": [
            {"n": i, **p.to_dict()}
            for i, p in enumerate(
                sorted(passages, key=lambda p: (-p.authority_rank, -p.score)), start=1
            )
        ],
        "authority": spread,
    }


def generate_scheme(
    *, learning_area, grade, term, year,
    weeks=10, lessons_per_week=4, extra_instructions="",
    learning_area_id=None, school=None,
):
    """Draft a scheme of work. `learning_area` is the subject name."""
    grounding = retrieve_grounding(
        learning_area_name=learning_area,
        learning_area_id=learning_area_id,
        grade=grade,
        term=term,
        school=school,
    )
    provenance = _grounding_note(grounding)

    if not _ai_configured():
        scheme = _stub_scheme(learning_area, grade, weeks, lessons_per_week, grounding)
        scheme["grounding"] = provenance
        return scheme

    import anthropic

    client = anthropic.Anthropic()
    level = level_of(grade)

    context_block = (
        f"\n\nCURRICULUM CONTEXT — work from these passages and cite them by "
        f"number in each lesson's `sources`:\n\n{grounding['context']}\n"
        if grounding["context"]
        else "\n\nNo curriculum documents were available for this subject and grade. "
        "Say so by leaving `sources` empty, and keep strictly to well-established "
        "KICD structure rather than inventing specific strand names.\n"
    )

    prompt = (
        f"Create a scheme of work for the Kenyan Competency-Based Curriculum.\n"
        f"Learning area: {learning_area}\n"
        f"Grade: {grade}"
        + (f" ({level['name']})" if level else "")
        + f"\nTerm: {term}, Year: {year}\n"
        f"Plan {weeks} weeks with {lessons_per_week} lessons per week.\n"
        f"Use real strands and sub-strands in curriculum order, lesson-level "
        f"outcomes ('By the end of the lesson the learner should be able to...'), "
        f"learner-centred experiences, key inquiry questions, locally available "
        f"resources, and CBC-appropriate assessment methods.\n"
        + (f"Additional instructions from the teacher: {extra_instructions}\n"
           if extra_instructions else "")
        + context_block
    )

    response = client.messages.create(
        model="claude-opus-5",
        max_tokens=16000,
        system=(
            "You are a Kenyan CBC curriculum specialist writing schemes of work for "
            "head-teacher review.\n\n"
            "Ground every strand and sub-strand in the curriculum context you are "
            "given, and cite the passage numbers you used. Do not invent strand "
            "names that contradict the context.\n\n"
            "Passages are presented highest-authority first and each is labelled. "
            "Where two sources conflict, follow the higher authority: Ministry of "
            "Education, then KICD, then KNEC, then a county office, then the "
            "school's own documents. The Ministry of Education structure governs.\n\n"
            "If the context does not cover part of the term, write that part from "
            "well-established KICD structure and leave its `sources` empty rather "
            "than attributing it to a passage."
        ),
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": SCHEME_JSON_SCHEMA}},
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("The model declined to generate this scheme.")

    text = next(block.text for block in response.content if block.type == "text")
    scheme = json.loads(text)
    scheme["generator"] = response.model
    scheme["grounding"] = provenance
    return scheme
