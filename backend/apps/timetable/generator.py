"""Greedy timetable generation over the clash-detection data model.

Strategy: most-constrained-first (highest weekly load), spreading each
requirement across days (never two lessons of the same area for the same class
on one day until every day has one). A slot is usable when the teacher, the
class (grade+stream), and — for lab subjects — a lab room are all free.
Greedy is deliberate for v1: it is fast, deterministic, and reports what it
could not place instead of silently overbooking; swap in a CP-SAT solver later
without touching the data model.
"""

from collections import defaultdict

from django.db import transaction

from .models import Lesson, LessonRequirement, Period, Room


@transaction.atomic
def generate_timetable(school, clear_existing: bool = True) -> dict:
    """Generate, retrying with different scan rotations until clean.

    Near teacher saturation (every week filled to the brim) a single greedy
    pass can strand a few lessons. Each seed shifts where every scan starts,
    which lands the pieces in a different order; the first perfect attempt
    wins, else the best of eight stands.
    """
    if not clear_existing:
        return _generate_once(school, clear_existing=False, seed=0)

    best_report, best_seed = None, 0
    for seed in range(8):
        report = _generate_once(school, clear_existing=True, seed=seed)
        if not report["unplaced"]:
            report["attempts"] = seed + 1
            return report
        if best_report is None or len(report["unplaced"]) < len(best_report["unplaced"]):
            best_report, best_seed = report, seed
    if best_seed != 7:
        best_report = _generate_once(school, clear_existing=True, seed=best_seed)
    best_report["attempts"] = 8
    return best_report


def _generate_once(school, *, clear_existing: bool, seed: int) -> dict:
    periods = list(Period.objects.filter(school=school).order_by("number"))
    days = [d for d, _ in Lesson.Day.choices]
    labs = list(Room.objects.filter(school=school, is_lab=True))

    if clear_existing:
        Lesson.objects.filter(school=school).delete()

    # Occupancy indexes, seeded from surviving lessons.
    teacher_busy = defaultdict(set)   # (day, period_id) -> {teacher_id}
    class_busy = defaultdict(set)     # (day, period_id) -> {(grade, stream)}
    lab_busy = defaultdict(set)       # (day, period_id) -> {room_id}
    for lesson in Lesson.objects.filter(school=school):
        slot = (lesson.day, lesson.period_id)
        teacher_busy[slot].add(lesson.teacher_id)
        class_busy[slot].add((lesson.grade, lesson.stream))
        if lesson.room_id:
            lab_busy[slot].add(lesson.room_id)

    # The generator schedules Grade 4 to Grade 9 only. Below that, the class
    # teacher takes their class through every learning area whole-day — a
    # timetable would be noise. Assignments for lower grades still exist (they
    # power the teacher's portal); they are just not scheduled.
    all_requirements = LessonRequirement.objects.filter(school=school)
    requirements = list(
        all_requirements.filter(grade__gte=4, grade__lte=9)
        .select_related("teacher", "learning_area")
    )
    lower_grades_skipped = all_requirements.exclude(
        grade__gte=4, grade__lte=9
    ).count()

    # Most-constrained first: a teacher carrying 30 lessons across six classes
    # (the school's only Social Studies teacher, say) must place before staff
    # with slack, or the free slots they need are gone by the time they play.
    teacher_total = defaultdict(int)
    for req in requirements:
        teacher_total[req.teacher_id] += req.lessons_per_week
    requirements.sort(
        key=lambda r: (
            -teacher_total[r.teacher_id],
            -r.lessons_per_week,
            # Seed-dependent tie-break: equal-constraint requirements play in a
            # different order each retry, exploring different layouts.
            (r.id * 7 + seed * 13) % 11,
            r.id,
        )
    )

    # Who is teaching where, as live Lesson objects — the swap and chain
    # passes move them. Indexed from both ends of each lesson.
    lesson_at = {}        # (day, period_id, teacher_id) -> Lesson
    class_lesson_at = {}  # (day, period_id, grade, stream) -> Lesson
    for lesson in Lesson.objects.filter(school=school):
        lesson_at[(lesson.day, lesson.period_id, lesson.teacher_id)] = lesson
        class_lesson_at[
            (lesson.day, lesson.period_id, lesson.grade, lesson.stream)
        ] = lesson

    def record(lesson):
        slot = (lesson.day, lesson.period_id)
        teacher_busy[slot].add(lesson.teacher_id)
        class_busy[slot].add((lesson.grade, lesson.stream))
        if lesson.room_id:
            lab_busy[slot].add(lesson.room_id)
        lesson_at[(lesson.day, lesson.period_id, lesson.teacher_id)] = lesson
        class_lesson_at[
            (lesson.day, lesson.period_id, lesson.grade, lesson.stream)
        ] = lesson

    def erase(lesson):
        slot = (lesson.day, lesson.period_id)
        teacher_busy[slot].discard(lesson.teacher_id)
        class_busy[slot].discard((lesson.grade, lesson.stream))
        if lesson.room_id:
            lab_busy[slot].discard(lesson.room_id)
        lesson_at.pop((lesson.day, lesson.period_id, lesson.teacher_id), None)
        class_lesson_at.pop(
            (lesson.day, lesson.period_id, lesson.grade, lesson.stream), None
        )

    def fits(teacher_id, grade, stream, day, period):
        slot = (day, period.id)
        return (
            teacher_id not in teacher_busy[slot]
            and (grade, stream) not in class_busy[slot]
        )

    def scan_order(req_id, day):
        # Rotate where the scan starts per requirement and day, so the same
        # subject doesn't sit at the same time every single day — a Monday
        # that equals Tuesday equals Friday is not a timetable. The seed
        # shifts every rotation, giving each retry a genuinely new layout.
        offset = (req_id * 3 + day * 2 + seed * 5) % len(periods) if periods else 0
        return periods[offset:] + periods[:offset]

    def try_swap(req, day_load):
        """The class is free somewhere but the teacher is booked everywhere the
        class is free. Move one of the teacher's other lessons aside — same day,
        different period first (nobody's weekly spread disturbed); failing that,
        any free slot in the blocker's week."""
        for day in sorted(days, key=lambda d: (day_load[d], d)):
            for period in scan_order(req.id, day):
                slot = (day, period.id)
                if (req.grade, req.stream) in class_busy[slot]:
                    continue
                blocker = lesson_at.get((day, period.id, req.teacher_id))
                if blocker is None:
                    continue
                relocations = [
                    (day, p) for p in scan_order(blocker.id, day) if p.id != period.id
                ] + [
                    (d2, p) for d2 in days if d2 != day
                    for p in scan_order(blocker.id, d2)
                ]
                for new_day, new_period in relocations:
                    if new_day == day and new_period.id == period.id:
                        continue
                    if not fits(blocker.teacher_id, blocker.grade, blocker.stream,
                                new_day, new_period):
                        continue
                    erase(blocker)
                    blocker.day = new_day
                    blocker.period = new_period
                    blocker.save(update_fields=["day", "period"])
                    record(blocker)
                    return (day, period, None)
        return None

    def try_chain(req):
        """König's escape hatch. The teacher has SOME free slot (alpha) and the
        class has SOME free slot (beta), they just never line up. In the
        two-slot world {alpha, beta}, the busy lessons form an alternating
        path; shifting every lesson on it to the other slot is always legal,
        and afterwards the two frees line up. Bipartite edge-colouring
        guarantees this terminates — it is why a full timetable always exists
        when nobody exceeds the week."""
        all_slots = [(d, p) for d in days for p in periods]
        class_free = [
            (d, p) for d, p in all_slots
            if (req.grade, req.stream) not in class_busy[(d, p.id)]
        ]
        teacher_free = [
            (d, p) for d, p in all_slots
            if req.teacher_id not in teacher_busy[(d, p.id)]
        ]
        for beta in class_free[:20]:
            for alpha in teacher_free[:20]:
                if (alpha[0], alpha[1].id) == (beta[0], beta[1].id):
                    continue
                # Walk the alternating path starting from the teacher's lesson
                # at beta, hopping between the two slots.
                path, seen, ok = [], set(), True
                kind, ident, slot = "T", req.teacher_id, beta
                while True:
                    day_, period_ = slot
                    lesson = (
                        lesson_at.get((day_, period_.id, ident))
                        if kind == "T"
                        else class_lesson_at.get((day_, period_.id, *ident))
                    )
                    if lesson is None:
                        break
                    if lesson.id in seen:
                        ok = False
                        break
                    seen.add(lesson.id)
                    path.append((lesson, slot))
                    kind, ident = (
                        ("C", (lesson.grade, lesson.stream)) if kind == "T"
                        else ("T", lesson.teacher_id)
                    )
                    slot = alpha if slot == beta else beta
                if not ok:
                    continue
                original = [(lesson, lesson.day, lesson.period) for lesson, _ in path]
                for lesson, _slot in path:
                    erase(lesson)
                for lesson, slot_ in path:
                    new_day, new_period = alpha if slot_ == beta else beta
                    lesson.day, lesson.period = new_day, new_period
                    record(lesson)
                landing = next(
                    (s for s in (beta, alpha)
                     if fits(req.teacher_id, req.grade, req.stream, s[0], s[1])),
                    None,
                )
                if landing is not None:
                    for lesson, _d, _p in original:
                        lesson.save(update_fields=["day", "period"])
                    return (landing[0], landing[1], None)
                # The flip didn't open a slot here — put everything back.
                for lesson, _slot in path:
                    erase(lesson)
                for lesson, day_, period_ in original:
                    lesson.day, lesson.period = day_, period_
                    record(lesson)
        return None

    placed = 0
    missed = defaultdict(int)  # requirement -> lessons that found no slot
    for req in requirements:
        day_load = defaultdict(int)  # lessons of THIS requirement already on each day
        for _ in range(req.lessons_per_week):
            # Prefer days this requirement hasn't used yet, then earliest periods.
            candidate_days = sorted(days, key=lambda d: (day_load[d], d))
            slot_found = None
            for day in candidate_days:
                for period in scan_order(req.id, day):
                    slot = (day, period.id)
                    if req.teacher_id in teacher_busy[slot]:
                        continue
                    if (req.grade, req.stream) in class_busy[slot]:
                        continue
                    room = None
                    if req.needs_lab:
                        room = next((l for l in labs if l.id not in lab_busy[slot]), None)
                        if room is None:
                            continue
                    slot_found = (day, period, room)
                    break
                if slot_found:
                    break

            if slot_found is None and not req.needs_lab:
                slot_found = try_swap(req, day_load)
            if slot_found is None and not req.needs_lab:
                slot_found = try_chain(req)
            if slot_found is None:
                missed[req] += 1
                continue

            day, period, room = slot_found
            lesson = Lesson.objects.create(
                school=school, day=day, period=period, teacher=req.teacher,
                learning_area=req.learning_area, grade=req.grade, stream=req.stream, room=room,
            )
            record(lesson)
            day_load[day] += 1
            placed += 1

    unplaced = [
        f"{req} ({count} of {req.lessons_per_week})"
        for req, count in missed.items()
    ]
    return {
        "placed": placed,
        "unplaced": unplaced,
        "requirements": len(requirements),
        "slots_available": len(periods) * len(days),
        "lower_grades_skipped": lower_grades_skipped,
    }


# Subjects that absorb the spare slots when a class has fewer subjects than
# the week has periods — the school day's heavyweights, in bump order.
CORE_SUBJECTS = ["English", "Kiswahili", "Mathematics"]


def auto_assign(school):
    """Build the G4-G9 teaching assignments from what the school already
    recorded: each grade's learning areas, each teacher's subjects and phase,
    and the streams its classes run.

    Every class's week is filled COMPLETELY: the week's slots (periods x 5
    days) are shared out across its teachable subjects, core subjects taking
    the extras — eight subjects over 45 slots means English, Kiswahili and
    Mathematics run at 6 lessons, not that the class sits idle. Re-running
    rebalances existing assignments to that distribution (respecting a
    teacher's own 45-slot week) and only fills what is missing. Areas nobody
    is qualified to teach are reported, not guessed.
    """
    from apps.assessments.models import LearningArea
    from apps.students.models import ClassGroup
    from apps.teachers.models import Teacher

    teachers = list(
        Teacher.objects.filter(school=school, user__is_active=True)
        .select_related("user")
        .prefetch_related("learning_areas")
    )
    subject_ids = {t.id: {a.id for a in t.learning_areas.all()} for t in teachers}

    week_slots = (Period.objects.filter(school=school).count() or 9) * 5
    load = defaultdict(int)
    existing = {}
    for req in LessonRequirement.objects.filter(school=school):
        load[req.teacher_id] += req.lessons_per_week
        existing[(req.grade, req.stream, req.learning_area_id)] = req

    streams_by_grade = defaultdict(set)
    for group in ClassGroup.objects.filter(school=school):
        streams_by_grade[group.grade].add(group.stream)

    def bump_order(area):
        name = area.name
        return (
            CORE_SUBJECTS.index(name) if name in CORE_SUBJECTS else len(CORE_SUBJECTS),
            name,
        )

    areas = list(LearningArea.objects.all())
    created = skipped_existing = rebalanced = 0
    unfilled = []
    for grade in range(4, 10):
        grade_areas = sorted(
            (a for a in areas if grade in (a.grades or [])), key=bump_order
        )
        streams = sorted(streams_by_grade.get(grade) or {""})
        for stream in streams:
            # Which of this class's areas can actually be taught — an existing
            # assignment, or at least one qualified teacher with room to spare.
            teachable, cands = [], {}
            for area in grade_areas:
                if (grade, stream, area.id) in existing:
                    teachable.append(area)
                    continue
                cands[area.id] = [
                    t for t in teachers
                    if t.may_teach_grade(grade) and area.id in subject_ids[t.id]
                ]
                if cands[area.id]:
                    teachable.append(area)
                else:
                    unfilled.append({
                        "grade": grade, "stream": stream, "area": area.name,
                    })
            if not teachable:
                continue

            # Share the whole week out: base for everyone, +1 to the first
            # `remainder` areas in bump order (cores first).
            base = week_slots // len(teachable)
            remainder = week_slots % len(teachable)
            weekly = {
                area.id: base + (1 if i < remainder else 0)
                for i, area in enumerate(teachable)
            }

            for area in teachable:
                target = weekly[area.id]
                req = existing.get((grade, stream, area.id))
                if req is not None:
                    delta = target - req.lessons_per_week
                    if delta and load[req.teacher_id] + delta <= week_slots:
                        req.lessons_per_week = target
                        req.save(update_fields=["lessons_per_week"])
                        load[req.teacher_id] += delta
                        rebalanced += 1
                    else:
                        skipped_existing += 1
                    continue
                fitting = [
                    t for t in cands[area.id] if load[t.id] + target <= week_slots
                ]
                if not fitting:
                    unfilled.append({
                        "grade": grade, "stream": stream, "area": area.name,
                    })
                    continue
                best = min(fitting, key=lambda t: load[t.id])
                req = LessonRequirement.objects.create(
                    school=school, teacher=best, learning_area=area,
                    grade=grade, stream=stream, lessons_per_week=target,
                )
                existing[(grade, stream, area.id)] = req
                load[best.id] += target
                created += 1
    return {
        "created": created,
        "skipped_existing": skipped_existing,
        "rebalanced": rebalanced,
        "unfilled": unfilled,
    }


# The standard Kenyan school day the user-facing button loads:
# two lessons, break, two lessons, break, two lessons, lunch, three lessons,
# then preps (not a lesson slot, so not a period).
STANDARD_DAY = [
    (1, "07:30", "08:15"),
    (2, "08:15", "09:00"),
    # 09:00-09:30 break
    (3, "09:30", "10:15"),
    (4, "10:15", "11:00"),
    # 11:00-11:30 break
    (5, "11:30", "12:15"),
    (6, "12:15", "13:00"),
    # 13:00-14:00 lunch
    (7, "14:00", "14:40"),
    (8, "14:40", "15:20"),
    (9, "15:20", "16:00"),
    # 16:00-17:00 preps
]


def seed_standard_day(school):
    """Create or align the school's periods to the standard day. Idempotent."""
    from datetime import time

    created = 0
    for number, start, end in STANDARD_DAY:
        start_t = time(*map(int, start.split(":")))
        end_t = time(*map(int, end.split(":")))
        _, was_created = Period.objects.update_or_create(
            school=school, number=number,
            defaults={"start_time": start_t, "end_time": end_t},
        )
        created += int(was_created)
    return created
