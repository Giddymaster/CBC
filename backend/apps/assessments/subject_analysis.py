"""How each subject is going across the school.

The teacher view answers "how are this teacher's classes doing". This answers
the other question a head asks in week ten: "which subject is the school
struggling with, and in which grade".

Same two guards as the teacher analysis, for the same reasons:

- **A minimum cohort.** A subject taught to four learners is not comparable to
  one taught to two hundred, so its mean is withheld rather than ranked.
- **Ranking is by learners reached, not just by mean.** A subject where 90% are
  at or above expectation across 200 learners is a different fact from one
  where 90% are across 6, and the response is presented so a head can see which
  they are looking at.
"""

from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.schools.moe import GRADE_LABELS
from apps.teachers.analysis import MIN_COHORT, competency_spread

from .models import Assessment, Score


def _percent(score):
    return (float(score.marks) / (score.assessment.max_marks or 100)) * 100


def subject_analysis(school, *, year=None, term=None, grade=None):
    """Every learning area with marks in this school, weakest first."""
    assessments = Assessment.objects.filter(school=school).select_related("learning_area")
    if year:
        assessments = assessments.filter(year=year)
    if term:
        assessments = assessments.filter(term=term)
    if grade is not None:
        assessments = assessments.filter(grade=grade)

    scores = list(
        Score.objects.filter(assessment__in=assessments).select_related(
            "assessment", "assessment__learning_area", "learner"
        )
    )
    if not scores:
        return {
            "school": school.name,
            "subjects": [],
            "note": (
                "No marks match this term and year yet. Subject outcomes appear "
                "once assessments have been marked."
            ),
        }

    by_area = {}
    for score in scores:
        area = score.assessment.learning_area
        by_area.setdefault(area.id, {"name": area.name, "scores": []})
        by_area[area.id]["scores"].append(score)

    subjects = []
    for area_id, bucket in by_area.items():
        rows = bucket["scores"]
        learners = {s.learner_id for s in rows}
        enough = len(learners) >= MIN_COHORT
        percents = [_percent(s) for s in rows]

        # Per grade, because "Mathematics is weak" is not actionable but
        # "Mathematics in Grade 8" is.
        grades = {}
        for score in rows:
            g = score.assessment.grade
            grades.setdefault(g, []).append(score)
        per_grade = []
        for g, g_scores in sorted(grades.items()):
            g_learners = {s.learner_id for s in g_scores}
            g_percents = [_percent(s) for s in g_scores]
            g_enough = len(g_learners) >= MIN_COHORT
            per_grade.append(
                {
                    "grade": g,
                    "grade_label": GRADE_LABELS.get(g, f"Grade {g}"),
                    "learners": len(g_learners),
                    "mean": round(sum(g_percents) / len(g_percents), 1) if g_enough else None,
                    "withheld": not g_enough,
                    "competency": competency_spread(g_scores),
                }
            )

        # Terms, so movement is visible at subject level too.
        by_term = {}
        for score in rows:
            key = (score.assessment.year, score.assessment.term)
            by_term.setdefault(key, []).append(_percent(score))
        timeline = [
            {"year": y, "term": t, "label": f"T{t} {y}", "mean": round(sum(v) / len(v), 1)}
            for (y, t), v in sorted(by_term.items())
        ]
        movement = (
            round(timeline[-1]["mean"] - timeline[-2]["mean"], 1)
            if len(timeline) >= 2
            else None
        )

        # Who teaches it — the head's next step after spotting a weak subject.
        from apps.timetable.models import LessonRequirement

        teachers = sorted(
            {
                req.teacher.user.get_full_name() or req.teacher.user.username
                for req in LessonRequirement.objects.filter(
                    school=school, learning_area_id=area_id
                ).select_related("teacher__user")
            }
        )

        subjects.append(
            {
                "learning_area": area_id,
                "name": bucket["name"],
                "learners": len(learners),
                "scores": len(rows),
                "mean": round(sum(percents) / len(percents), 1) if enough else None,
                "withheld": not enough,
                "withheld_reason": (
                    None if enough
                    else f"Fewer than {MIN_COHORT} learners — too few to compare."
                ),
                "competency": competency_spread(rows),
                "movement": movement,
                "timeline": timeline,
                "grades": per_grade,
                "teachers": teachers,
            }
        )

    # Weakest first: this list exists to be acted on, and a subject that is
    # going well needs no attention. Withheld ones sort last.
    subjects.sort(
        key=lambda s: (
            s["mean"] is None,
            s["competency"]["at_or_above_expectation"]
            if s["competency"]["at_or_above_expectation"] is not None
            else 999,
        )
    )
    ranked = [s for s in subjects if s["mean"] is not None]
    return {
        "school": school.name,
        "subjects": subjects,
        "weakest": ranked[0]["name"] if ranked else None,
        "strongest": ranked[-1]["name"] if ranked else None,
        "note": (
            "Ordered weakest first — this list exists to be acted on. Subjects are "
            "taught to different numbers of learners in different grades, so read "
            "the cohort size beside the mean."
        ),
    }


class SubjectAnalysisView(APIView):
    """GET /api/school/subject-analysis/?year=&term=&grade=

    Whole-school, so it is for whoever already sees the whole school: the
    admin, the head, or a deputy.
    """

    def get(self, request):
        user = request.user
        if not (user.is_superuser or user.role == "ADMIN"):
            from apps.teachers.supervision import SCOPE_WHOLE_SCHOOL, rank_level

            if rank_level(user) < SCOPE_WHOLE_SCHOOL:
                raise PermissionDenied(
                    "Only the head teacher, deputy or admin sees the whole school."
                )

        def as_int(name):
            raw = request.query_params.get(name)
            return int(raw) if raw not in (None, "") else None

        try:
            year, term, grade = as_int("year"), as_int("term"), as_int("grade")
        except ValueError:
            return Response(
                {"detail": "year, term and grade must be numbers."}, status=400
            )
        return Response(
            subject_analysis(user.school, year=year, term=term, grade=grade)
        )
