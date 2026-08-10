"""Admin school-structure views.

- GET /api/school/structure/          -> categories (Primary / JSS / Senior) with
                                         per-grade enrolment counts and class teachers
- GET /api/school/grades/<grade>/     -> one grade: students (+today's attendance),
                                         class teacher panel, timetable
Query param ?stream= narrows a grade to one class.
"""

from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.attendance.models import AttendanceRecord
from apps.students.models import ClassGroup, Learner
from apps.teachers.models import TeacherAttendance
from apps.timetable.models import Lesson, LessonRequirement

CATEGORIES = [
    ("Pre-Primary", [-2, -1, 0]),
    ("Primary", [1, 2, 3, 4, 5, 6]),
    ("Junior School", [7, 8, 9]),
    ("Senior School", [10, 11, 12]),
]

GRADE_LABELS = {
    -2: "PG", -1: "PP1", 0: "PP2", **{g: f"Grade {g}" for g in range(1, 13)}
}


def _require_staff(user):
    if not (user.is_superuser or user.role in ("ADMIN", "TEACHER")):
        raise PermissionDenied("Staff only.")


def _teacher_panel(teacher, school, grade, stream, today):
    """Everything the admin wants to know about a class teacher at a glance."""
    if teacher is None:
        return None

    attendance_today = TeacherAttendance.objects.filter(teacher=teacher, date=today).first()
    roll_call_taken = AttendanceRecord.objects.filter(
        school=school, date=today, learner__grade=grade, learner__stream=stream
    ).exists()

    def short_label(g):
        return GRADE_LABELS[g] if g < 1 else f"G{g}"

    lessons = [
        {"subject": subject, "grade": g, "grade_label": short_label(g)}
        for subject, g in sorted(
            set(
                LessonRequirement.objects.filter(teacher=teacher)
                .select_related("learning_area")
                .values_list("learning_area__name", "grade")
            )
        )
    ]
    schemes = [
        {
            "id": s.id,
            "learning_area": s.learning_area.name,
            "grade": s.grade,
            "term": s.term,
            "year": s.year,
            "status": s.status,
        }
        for s in teacher.schemes.select_related("learning_area").order_by("-year", "-term")
    ]
    timetable = [
        {
            "day": lesson.day,
            "day_name": lesson.get_day_display(),
            "period": lesson.period.number,
            "start": lesson.period.start_time.strftime("%H:%M"),
            "end": lesson.period.end_time.strftime("%H:%M"),
            "learning_area": lesson.learning_area.name,
            "grade": lesson.grade,
            "stream": lesson.stream,
        }
        for lesson in Lesson.objects.filter(teacher=teacher)
        .select_related("period", "learning_area")
        .order_by("day", "period__number")
    ]
    return {
        "id": teacher.id,
        "name": teacher.user.get_full_name() or teacher.user.username,
        "tsc_number": teacher.tsc_number,
        "present_today": attendance_today.status if attendance_today else None,
        "roll_call_taken_today": roll_call_taken,
        "lessons": lessons,
        "schemes_of_work": schemes,
        "timetable": timetable,
    }


class GradeStreamsView(APIView):
    """GET /api/school/streams/?grade=N — the streams a grade actually runs.

    Union of the class groups the school defined and the streams its learners
    are really in: a stream picker built from ClassGroup alone goes blind to
    learners imported into a stream nobody created a class group for.
    """

    def get(self, request):
        _require_staff(request.user)
        school = request.user.school
        grade = request.query_params.get("grade")

        groups = ClassGroup.objects.filter(school=school)
        learners = Learner.objects.filter(school=school, active=True)
        if grade not in (None, ""):
            groups = groups.filter(grade=int(grade))
            learners = learners.filter(grade=int(grade))

        streams = {s for s in groups.values_list("stream", flat=True) if s}
        streams |= {s for s in learners.values_list("stream", flat=True) if s}
        # Learners with no stream at all are still somebody's class.
        unstreamed = learners.filter(stream="").exists()
        return Response({"streams": sorted(streams), "unstreamed": unstreamed})


class SchoolStructureView(APIView):
    def get(self, request):
        _require_staff(request.user)
        school = request.user.school

        counts = {}
        for row in (
            Learner.objects.filter(school=school, active=True)
            .values("grade", "gender")
            .order_by()
        ):
            slot = counts.setdefault(row["grade"], {"male": 0, "female": 0})
            slot["male" if row["gender"] == "M" else "female"] += 1

        class_teachers = {}
        for group in ClassGroup.objects.filter(school=school).select_related(
            "class_teacher__user"
        ):
            class_teachers.setdefault(group.grade, []).append(
                {
                    "id": group.id,
                    "stream": group.stream,
                    "class_teacher": (
                        group.class_teacher.user.get_full_name()
                        if group.class_teacher
                        else None
                    ),
                }
            )

        categories = []
        for name, grades in CATEGORIES:
            categories.append(
                {
                    "name": name,
                    "grades": [
                        {
                            "grade": g,
                            "label": GRADE_LABELS[g],
                            "male": counts.get(g, {}).get("male", 0),
                            "female": counts.get(g, {}).get("female", 0),
                            "total": sum(counts.get(g, {}).values()),
                            "classes": class_teachers.get(g, []),
                        }
                        for g in grades
                    ],
                }
            )
        return Response({"school": school.name, "categories": categories})


class GradeDetailView(APIView):
    def get(self, request, grade):
        _require_staff(request.user)
        school = request.user.school
        grade = int(grade)
        stream = request.query_params.get("stream", "")
        today = timezone.localdate()

        learners = Learner.objects.filter(school=school, grade=grade, active=True)
        if stream:
            learners = learners.filter(stream=stream)
        learners = learners.order_by("admission_number")

        attendance_today = {
            a.learner_id: a.status
            for a in AttendanceRecord.objects.filter(
                school=school, date=today, learner__in=learners
            )
        }
        students = [
            {
                "id": l.id,
                "admission_number": l.admission_number,
                "name": l.full_name,
                "gender": l.gender,
                "stream": l.stream,
                "upi": l.upi,
                "photo": request.build_absolute_uri(l.photo.url) if l.photo else None,
                "today": attendance_today.get(l.id),  # P/A/L/E or null (not marked)
            }
            for l in learners
        ]
        male = sum(1 for s in students if s["gender"] == "M")

        groups = ClassGroup.objects.filter(school=school, grade=grade).select_related(
            "class_teacher__user"
        )
        if stream:
            groups = groups.filter(stream=stream)
        class_teachers = [
            {
                "class_group_id": group.id,
                "stream": group.stream,
                **(
                    _teacher_panel(group.class_teacher, school, grade, group.stream, today)
                    or {"name": None}
                ),
            }
            for group in groups
        ]

        lessons = Lesson.objects.filter(school=school, grade=grade)
        if stream:
            lessons = lessons.filter(stream=stream)
        timetable = [
            {
                "day": lesson.day,
                "period": lesson.period.number,
                "start": lesson.period.start_time.strftime("%H:%M"),
                "end": lesson.period.end_time.strftime("%H:%M"),
                "learning_area": lesson.learning_area.name,
                "teacher": lesson.teacher.user.get_full_name()
                or lesson.teacher.user.username,
                "stream": lesson.stream,
                "room": lesson.room.name if lesson.room else None,
            }
            for lesson in lessons.select_related(
                "period", "learning_area", "teacher__user", "room"
            ).order_by("day", "period__number")
        ]

        return Response(
            {
                "grade": grade,
                "label": GRADE_LABELS.get(grade, str(grade)),
                "stream": stream,
                "date": today.isoformat(),
                "totals": {
                    "students": len(students),
                    "male": male,
                    "female": len(students) - male,
                    "present_today": sum(1 for s in students if s["today"] == "P"),
                    "absent_today": sum(1 for s in students if s["today"] == "A"),
                    "unmarked_today": sum(1 for s in students if s["today"] is None),
                },
                "students": students,
                "class_teachers": class_teachers,
                "timetable": timetable,
            }
        )
