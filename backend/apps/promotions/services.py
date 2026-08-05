"""Building, applying and reversing a promotion run."""

from django.db import transaction
from django.utils import timezone

from apps.schools.moe import (
    PATHWAYS,
    next_grade,
    pathway_affinity,
    transition_from,
)
from apps.students.models import Learner, Pathway

from .models import PromotionOutcome, PromotionRun


def propose_pathway(learner):
    """Suggest a Senior School pathway from the learner's own record.

    Advisory only. MoE placement weighs KJSEA performance, the learner's choice
    and the receiving school's capacity — this reads the marks the school
    already holds and says which pathway they point at, with the reasoning
    attached so the head can disagree.

    Returns (pathway_code | None, rationale dict).
    """
    from apps.assessments.models import Score

    scores = (
        Score.objects.filter(learner=learner)
        .select_related("assessment__learning_area")
        .order_by("-assessment__year", "-assessment__term")
    )

    totals = {code: [] for code in (p["code"] for p in PATHWAYS)}
    subjects_seen = {}
    for score in scores:
        area = score.assessment.learning_area
        code = pathway_affinity(area.name)
        if code is None:
            continue
        max_marks = score.assessment.max_marks or 100
        percent = (float(score.marks) / max_marks) * 100
        totals[code].append(percent)
        subjects_seen.setdefault(code, set()).add(area.name)

    averages = {
        code: round(sum(values) / len(values), 1)
        for code, values in totals.items()
        if values
    }
    if not averages:
        return None, {
            "basis": "no marks on record",
            "note": "Nothing to go on — the head must choose the pathway.",
        }

    best = max(averages, key=averages.get)
    ranked = sorted(averages.items(), key=lambda kv: -kv[1])
    return best, {
        "basis": "mean percentage in subjects associated with each pathway",
        "averages": averages,
        "ranked": [code for code, _ in ranked],
        "subjects": {code: sorted(names) for code, names in subjects_seen.items()},
        "note": (
            "Advisory. MoE placement also weighs KJSEA performance, the "
            "learner's own choice and the receiving school's capacity."
        ),
    }


def build_run(*, school, from_year, to_year, grade=None, user=None, note=""):
    """Create a DRAFT run with one outcome per active learner. Changes nothing."""
    learners = Learner.objects.filter(school=school, active=True)
    if grade is not None:
        learners = learners.filter(grade=grade)

    with transaction.atomic():
        run = PromotionRun.objects.create(
            school=school,
            from_year=from_year,
            to_year=to_year,
            grade=grade,
            created_by=user,
            note=note,
        )
        outcomes = []
        for learner in learners.select_related("pathway"):
            target = next_grade(learner.grade)
            if target is None:
                # Grade 12 is the end of basic education.
                outcomes.append(
                    PromotionOutcome(
                        school=school, run=run, learner=learner,
                        action=PromotionOutcome.Action.GRADUATE,
                        to_grade=None,
                    )
                )
                continue

            outcome = PromotionOutcome(
                school=school, run=run, learner=learner,
                action=PromotionOutcome.Action.PROMOTE,
                to_grade=target,
                to_stream=learner.stream,
            )
            # The one transition that assigns a pathway.
            move = transition_from(learner.grade)
            if move and move["selects_pathway"]:
                code, rationale = propose_pathway(learner)
                outcome.pathway_rationale = rationale
                if code:
                    outcome.pathway = Pathway.objects.filter(code=code).first()
            outcomes.append(outcome)

        PromotionOutcome.objects.bulk_create(outcomes)
    return run


def apply_run(run, *, user=None):
    """Commit the run, recording each learner's prior state for reversal."""
    if run.status != PromotionRun.Status.DRAFT:
        raise ValueError("Only a draft run can be applied.")

    with transaction.atomic():
        outcomes = list(
            run.outcomes.select_related("learner", "pathway", "learner__pathway")
        )
        for outcome in outcomes:
            learner = outcome.learner
            outcome.previous_grade = learner.grade
            outcome.previous_stream = learner.stream
            outcome.previous_pathway = learner.pathway
            outcome.previous_status = learner.status
            outcome.previous_active = learner.active

            if outcome.action == PromotionOutcome.Action.PROMOTE:
                learner.grade = outcome.to_grade
                learner.stream = outcome.to_stream
                if outcome.pathway_id:
                    learner.pathway = outcome.pathway
            elif outcome.action == PromotionOutcome.Action.REPEAT:
                pass  # stays exactly where they are
            elif outcome.action == PromotionOutcome.Action.TRANSFER_OUT:
                learner.status = Learner.Status.TRANSFERRED
                learner.active = False
                learner.exit_date = timezone.localdate()
                learner.exit_note = outcome.note
            elif outcome.action == PromotionOutcome.Action.GRADUATE:
                learner.status = Learner.Status.GRADUATED
                learner.active = False
                learner.exit_date = timezone.localdate()

            learner.save()
            outcome.applied = True

        PromotionOutcome.objects.bulk_update(
            outcomes,
            [
                "previous_grade", "previous_stream", "previous_pathway",
                "previous_status", "previous_active", "applied", "updated_at",
            ],
        )

        run.status = PromotionRun.Status.APPLIED
        run.applied_at = timezone.now()
        run.applied_by = user
        run.save(update_fields=["status", "applied_at", "applied_by", "updated_at"])

        # Roll the school's calendar forward.
        from .models import AcademicYear

        AcademicYear.objects.filter(school=run.school, is_current=True).update(
            is_current=False
        )
        AcademicYear.objects.update_or_create(
            school=run.school, year=run.to_year, defaults={"is_current": True}
        )

    from apps.common.audit import record as audit

    audit(
        actor=user,
        school=run.school,
        action="PROMOTION_APPLIED",
        target=run,
        label=f"{run.from_year} to {run.to_year}",
        detail={"learners": len(outcomes)},
    )
    return run


def revert_run(run, *, user=None):
    """Put every learner back exactly as they were before the run."""
    if run.status != PromotionRun.Status.APPLIED:
        raise ValueError("Only an applied run can be reversed.")

    with transaction.atomic():
        for outcome in run.outcomes.select_related("learner"):
            if not outcome.applied:
                continue
            learner = outcome.learner
            learner.grade = outcome.previous_grade
            learner.stream = outcome.previous_stream
            learner.pathway = outcome.previous_pathway
            learner.status = outcome.previous_status or Learner.Status.ENROLLED
            learner.active = (
                True if outcome.previous_active is None else outcome.previous_active
            )
            if learner.status == Learner.Status.ENROLLED:
                learner.exit_date = None
                learner.exit_note = ""
            learner.save()

        run.outcomes.update(applied=False)
        run.status = PromotionRun.Status.REVERSED
        run.reversed_at = timezone.now()
        run.reversed_by = user
        run.save(update_fields=["status", "reversed_at", "reversed_by", "updated_at"])

        from .models import AcademicYear

        AcademicYear.objects.filter(school=run.school, is_current=True).update(
            is_current=False
        )
        # update_or_create, not update: a school that promoted without ever
        # recording the year it was closing would otherwise be left with no
        # current year at all.
        AcademicYear.objects.update_or_create(
            school=run.school, year=run.from_year, defaults={"is_current": True}
        )

    from apps.common.audit import record as audit

    audit(
        actor=user,
        school=run.school,
        action="PROMOTION_REVERSED",
        target=run,
        label=f"{run.from_year} to {run.to_year}",
    )
    return run


def summarise(run):
    """Counts per action, for the confirmation screen."""
    counts = {}
    for outcome in run.outcomes.all():
        counts[outcome.action] = counts.get(outcome.action, 0) + 1
    needs_pathway = run.outcomes.filter(
        action=PromotionOutcome.Action.PROMOTE, to_grade=10, pathway__isnull=True
    ).count()
    return {
        "total": run.outcomes.count(),
        "by_action": counts,
        "awaiting_pathway": needs_pathway,
    }
