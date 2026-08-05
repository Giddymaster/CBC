"""Teacher portal: one endpoint returning everything the teacher UI needs —
their timetable, the assessments they can enter scores for, their schemes of
work, and teacher-audience announcements."""

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.assessments.models import Assessment
from apps.communication.models import Announcement
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

        # Classes this teacher owns (from requirements; lessons as fallback),
        # then the assessments they can enter scores for.
        combos = set(
            LessonRequirement.objects.filter(teacher=teacher)
            .values_list("learning_area_id", "grade", "stream")
        ) | set(lessons.values_list("learning_area_id", "grade", "stream"))
        # A stream-blank assessment covers the whole grade.
        grade_combos = {(la, grade) for la, grade, _ in combos}

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
                "document": s.document.url if s.document else None,
                "review_comment": s.review_comment,
                "lesson_plans": s.lesson_plans.count(),
            }
            for s in teacher.schemes.select_related("learning_area").order_by("-year", "-term")
        ]

        taught_ids = set(teacher.learning_areas.values_list("id", flat=True)) | {
            la for la, _, _ in combos
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
