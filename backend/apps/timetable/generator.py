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
        key=lambda r: (-teacher_total[r.teacher_id], -r.lessons_per_week, r.id)
    )

    placed, unplaced = 0, []
    for req in requirements:
        day_load = defaultdict(int)  # lessons of THIS requirement already on each day
        for _ in range(req.lessons_per_week):
            # Prefer days this requirement hasn't used yet, then earliest periods.
            candidate_days = sorted(days, key=lambda d: (day_load[d], d))
            slot_found = None
            for day in candidate_days:
                for period in periods:
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

            if slot_found is None:
                unplaced.append(str(req))
                break

            day, period, room = slot_found
            Lesson.objects.create(
                school=school, day=day, period=period, teacher=req.teacher,
                learning_area=req.learning_area, grade=req.grade, stream=req.stream, room=room,
            )
            slot = (day, period.id)
            teacher_busy[slot].add(req.teacher_id)
            class_busy[slot].add((req.grade, req.stream))
            if room:
                lab_busy[slot].add(room.id)
            day_load[day] += 1
            placed += 1

    return {
        "placed": placed,
        "unplaced": unplaced,
        "requirements": len(requirements),
        "slots_available": len(periods) * len(days),
        "lower_grades_skipped": lower_grades_skipped,
    }


def auto_assign(school):
    """Build the G4-G9 teaching assignments from what the school already
    recorded: each grade's learning areas, each teacher's subjects and phase,
    and the streams its classes run.

    For every (grade, stream, learning area) without an assignment, the
    least-loaded qualified teacher — right phase (or unphased), subject on
    their record — gets it at 5 lessons/week. Areas nobody is qualified to
    teach are reported, not guessed.
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

    load = defaultdict(int)
    existing_keys = set()
    for req in LessonRequirement.objects.filter(school=school):
        load[req.teacher_id] += req.lessons_per_week
        existing_keys.add((req.grade, req.stream, req.learning_area_id))

    streams_by_grade = defaultdict(set)
    for group in ClassGroup.objects.filter(school=school):
        streams_by_grade[group.grade].add(group.stream)

    areas = list(LearningArea.objects.all())
    created, skipped_existing, unfilled = 0, 0, []
    for grade in range(4, 10):
        grade_areas = [a for a in areas if grade in (a.grades or [])]
        streams = sorted(streams_by_grade.get(grade) or {""})
        for stream in streams:
            for area in grade_areas:
                if (grade, stream, area.id) in existing_keys:
                    skipped_existing += 1
                    continue
                candidates = [
                    t for t in teachers
                    if t.may_teach_grade(grade)
                    and area.id in subject_ids[t.id]
                    and load[t.id] < 40  # keep everyone under a full week
                ]
                if not candidates:
                    unfilled.append({
                        "grade": grade, "stream": stream, "area": area.name,
                    })
                    continue
                best = min(candidates, key=lambda t: load[t.id])
                LessonRequirement.objects.create(
                    school=school, teacher=best, learning_area=area,
                    grade=grade, stream=stream, lessons_per_week=5,
                )
                existing_keys.add((grade, stream, area.id))
                load[best.id] += 5
                created += 1
    return {
        "created": created,
        "skipped_existing": skipped_existing,
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
