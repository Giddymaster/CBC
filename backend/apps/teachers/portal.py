"""Teacher portal: one endpoint returning everything the teacher UI needs —
their timetable, the assessments they can enter scores for, their schemes of
work, and teacher-audience announcements."""

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.assessments.models import Assessment
from apps.communication.models import Announcement
from apps.students.models import ClassGroup
from apps.timetable.models import Lesson, LessonRequirement


class TeacherSummaryView(APIView):
    def get(self, request):
        teacher = getattr(request.user, "teacher_profile", None)
        if teacher is None:
            return Response(
                {"detail": "This account is not linked to a teacher profile."}, status=403
            )

        lessons = (
            Lesson.objects.filter(teacher=teacher)
            .select_related("period", "learning_area", "room")
            .order_by("day", "period__number")
        )
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
                "room": lesson.room.name if lesson.room else None,
            }
            for lesson in lessons
        ]

        # Classes this teacher owns — what the timetable says they teach
        # (requirements; placed lessons as fallback). The head teacher and
        # deputy run the school, so they see every class-subject, not only
        # their own.
        from .supervision import SCOPE_WHOLE_SCHOOL, rank_level

        whole_school = rank_level(request.user) >= SCOPE_WHOLE_SCHOOL
        req_qs = LessonRequirement.objects.filter(school=teacher.school)
        if not whole_school:
            req_qs = req_qs.filter(teacher=teacher)
        combos = set(
            req_qs.values_list("learning_area_id", "grade", "stream")
        ) | set(lessons.values_list("learning_area_id", "grade", "stream"))
        # A stream-blank assessment covers the whole grade.
        grade_combos = {(la, grade) for la, grade, _ in combos}

        # The same combos with names, for the score-entry class bar.
        from apps.assessments.models import LearningArea

        area_names = dict(
            LearningArea.objects.filter(
                id__in={la for la, _, _ in combos}
            ).values_list("id", "name")
        )
        teaching_classes = sorted(
            (
                {
                    "grade": grade,
                    "stream": stream,
                    "learning_area_id": la,
                    "learning_area": area_names.get(la, ""),
                }
                for la, grade, stream in combos
            ),
            key=lambda c: (c["grade"], c["stream"], c["learning_area"]),
        )

        assessments = []
        for assessment in (
            Assessment.objects.filter(school=teacher.school)
            .select_related("learning_area")
            .order_by("-year", "-term", "learning_area__name")
        ):
            key = (assessment.learning_area_id, assessment.grade, assessment.stream)
            matches = (
                key in combos
                if assessment.stream
                else (assessment.learning_area_id, assessment.grade) in grade_combos
            )
            if matches:
                assessments.append(
                    {
                        "id": assessment.id,
                        "label": str(assessment),
                        "kind": assessment.kind,
                        "learning_area": assessment.learning_area.name,
                        "grade": assessment.grade,
                        "stream": assessment.stream,
                        "term": assessment.term,
                        "year": assessment.year,
                        "max_marks": assessment.max_marks,
                        # The banding, so the client can show the level live as
                        # marks are typed. The server still derives the stored
                        # level on save; this is preview, not authority.
                        "rubric": assessment.rubric,
                    }
                )

        schemes = [
            {
                "id": s.id,
                "learning_area": s.learning_area.name,
                "grade": s.grade,
                "term": s.term,
                "year": s.year,
                "status": s.status,
                "source": s.source,
                "document": (
                    request.build_absolute_uri(s.document.url) if s.document else None
                ),
                # The plan itself, so the teacher can proofread and edit it
                # here rather than fetching each scheme separately.
                "content": s.content or {},
                "review_comment": s.review_comment,
                "lesson_plans": s.lesson_plans.count(),
            }
            for s in teacher.schemes.select_related("learning_area").order_by("-year", "-term")
        ]

        # Subjects THIS teacher teaches — their own record and their own
        # timetable, never the school-wide set a head teacher can see. A
        # scheme of work is filed personally, and the server refuses one for a
        # subject the teacher does not teach, so the picker must not offer it.
        own_combos = set(
            LessonRequirement.objects.filter(teacher=teacher).values_list(
                "learning_area_id", "grade", "stream"
            )
        ) | set(lessons.values_list("learning_area_id", "grade", "stream"))
        taught_ids = set(teacher.learning_areas.values_list("id", flat=True)) | {
            la for la, _, _ in own_combos
        }
        from apps.assessments.models import LearningArea

        taught_learning_areas = [
            {"id": la.id, "name": la.name}
            for la in LearningArea.objects.filter(id__in=taught_ids).order_by("name")
        ]

        announcements = Announcement.objects.filter(
            school=teacher.school,
            audience__in=[Announcement.Audience.ALL, Announcement.Audience.TEACHERS],
        ).order_by("-created_at")[:10]

        return Response(
            {
                "teacher": {
                    "id": teacher.id,
                    "name": request.user.get_full_name() or request.user.username,
                    "tsc_number": teacher.tsc_number,
                    "school": teacher.school.name,
                },
                "timetable": timetable,
                "teaching_classes": teaching_classes,
                # The class(es) this teacher is seated over as CLASS teacher —
                # the only classes whose attendance register they may mark.
                "class_teacher_of": [
                    {"grade": g, "stream": s}
                    for g, s in ClassGroup.objects.filter(
                        class_teacher=teacher
                    ).values_list("grade", "stream")
                ],
                "assessments": assessments,
                "taught_learning_areas": taught_learning_areas,
                "schemes_of_work": schemes,
                "announcements": [
                    {
                        "id": a.id,
                        "title": a.title,
                        "body": a.body,
                        "meeting_link": a.meeting_link,
                        "date": a.created_at.date().isoformat(),
                    }
                    for a in announcements
                ],
            }
        )
