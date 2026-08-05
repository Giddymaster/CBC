"""Teacher analysis: what the marks say about a teacher's classes.

Deliberately framed as *the outcomes of the classes a teacher taught*, not as a
score for the teacher. A Grade 8 class that arrives two levels behind will show
a low mean however well it is taught, so every figure here is presented with the
context that makes it readable — the class, the subject, and what the same class
did last term.

Two guards against the numbers being read as more than they are:

- **A minimum cohort.** A mean over three learners is noise; below the threshold
  the figure is withheld rather than shown with a caveat nobody reads.
- **Movement over level.** Term-on-term change is the honest signal, because it
  compares a class with itself rather than with a different class.
"""

from django.db.models import Q

from apps.assessments.models import Assessment, CompetencyLevel, Score
from apps.schools.moe import GRADE_LABELS

# Below this a class mean says more about the sample than the teaching.
MIN_COHORT = 5


def _grade_label(grade):
    return GRADE_LABELS.get(grade, f"Grade {grade}")


def _percent(score):
    max_marks = score.assessment.max_marks or 100
    return (float(score.marks) / max_marks) * 100


def competency_spread(scores):
    """How a set of scores falls across EE/ME/AE/BE."""
    counts = {level: 0 for level, _ in CompetencyLevel.choices}
    for score in scores:
        counts[score.competency_level] = counts.get(score.competency_level, 0) + 1
    total = sum(counts.values())
    return {
        "counts": counts,
        "total": total,
        "percent": (
            {level: round(n * 100 / total, 1) for level, n in counts.items()}
            if total
            else {level: 0 for level in counts}
        ),
        # The figure a head actually acts on.
        "at_or_above_expectation": (
            round((counts["EE"] + counts["ME"]) * 100 / total, 1) if total else None
        ),
    }


def teacher_analysis(teacher, *, year=None, term=None):
    """One teacher's classes, subject by subject, with term-on-term movement."""
    assessments = Assessment.objects.filter(school=teacher.school)
    if year:
        assessments = assessments.filter(year=year)
    if term:
        assessments = assessments.filter(term=term)

    # The classes this teacher is responsible for, from their timetable.
    from apps.timetable.models import LessonRequirement

    taught = set(
        LessonRequirement.objects.filter(teacher=teacher).values_list(
            "learning_area_id", "grade", "stream"
        )
    )
    if not taught:
        return {
            "teacher": str(teacher),
            "classes": [],
            "note": (
                "No lesson requirements are recorded for this teacher, so there is "
                "nothing to attribute. Add them under the timetable."
            ),
        }

    rows = []
    for learning_area_id, grade, stream in sorted(taught, key=lambda t: (t[1], t[0])):
        relevant = assessments.filter(learning_area_id=learning_area_id, grade=grade)
        if stream:
            # A stream-blank assessment covers the whole grade.
            relevant = relevant.filter(Q(stream=stream) | Q(stream=""))

        score_qs = Score.objects.filter(assessment__in=relevant).select_related(
            "assessment", "assessment__learning_area", "learner"
        )
        if stream:
            # A grade-wide assessment still only counts this teacher's stream.
            score_qs = score_qs.filter(learner__stream=stream)
        scores = list(score_qs)
        if not scores:
            continue

        area_name = scores[0].assessment.learning_area.name
        percents = [_percent(s) for s in scores]
        learners = {s.learner_id for s in scores}

        # Term-on-term: mean per (year, term), oldest first.
        by_term = {}
        for score in scores:
            key = (score.assessment.year, score.assessment.term)
            by_term.setdefault(key, []).append(_percent(score))
        timeline = [
            {
                "year": y,
                "term": t,
                "label": f"T{t} {y}",
                "mean": round(sum(v) / len(v), 1),
                "learners": len(v),
            }
            for (y, t), v in sorted(by_term.items())
        ]
        movement = (
            round(timeline[-1]["mean"] - timeline[-2]["mean"], 1)
            if len(timeline) >= 2
            else None
        )

        enough = len(learners) >= MIN_COHORT
        rows.append(
            {
                "learning_area": area_name,
                "grade": grade,
                "grade_label": _grade_label(grade),
                "stream": stream,
                "learners": len(learners),
                "scores": len(scores),
                "mean": round(sum(percents) / len(percents), 1) if enough else None,
                "withheld": not enough,
                "withheld_reason": (
                    None if enough
                    else f"Fewer than {MIN_COHORT} learners — too few to read as a mean."
                ),
                "competency": competency_spread(scores),
                "timeline": timeline,
                "movement": movement,
            }
        )

    means = [r["mean"] for r in rows if r["mean"] is not None]
    return {
        "teacher": str(teacher),
        "teacher_id": teacher.id,
        "classes": rows,
        "overall_mean": round(sum(means) / len(means), 1) if means else None,
        "note": (
            "Figures describe the classes taught, not the teacher. Read the movement "
            "column before the mean: it compares a class with itself."
        ),
    }


def school_overview(school, *, year=None, term=None):
    """Every teacher's classes side by side, for the head."""
    from .models import Teacher

    teachers = Teacher.objects.filter(school=school, user__is_active=True).select_related(
        "user"
    )
    rows = []
    for teacher in teachers:
        analysis = teacher_analysis(teacher, year=year, term=term)
        if not analysis["classes"]:
            continue
        rows.append(
            {
                "teacher_id": teacher.id,
                "user_id": teacher.user_id,
                "name": teacher.user.get_full_name() or teacher.user.username,
                "rank": teacher.get_rank_display(),
                "classes": len(analysis["classes"]),
                "overall_mean": analysis["overall_mean"],
                "at_or_above": [
                    c["competency"]["at_or_above_expectation"] for c in analysis["classes"]
                ],
                "movements": [
                    c["movement"] for c in analysis["classes"] if c["movement"] is not None
                ],
            }
        )
    for row in rows:
        above = [v for v in row["at_or_above"] if v is not None]
        row["at_or_above_expectation"] = round(sum(above) / len(above), 1) if above else None
        row["movement"] = (
            round(sum(row["movements"]) / len(row["movements"]), 1)
            if row["movements"]
            else None
        )
        del row["at_or_above"], row["movements"]

    rows.sort(key=lambda r: (r["overall_mean"] is None, -(r["overall_mean"] or 0)))
    return {
        "school": school.name,
        "teachers": rows,
        "note": (
            "Classes differ in starting point, so this is not a ranking. It shows "
            "where to go and look."
        ),
    }
