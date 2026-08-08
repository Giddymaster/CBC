from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.views import AdminWriteMixin, SchoolScopedViewSet

from .generator import generate_timetable
from .models import Lesson, LessonRequirement, Period, Room
from .serializers import (
    LessonRequirementSerializer,
    LessonSerializer,
    PeriodSerializer,
    RoomSerializer,
)


class RoomViewSet(AdminWriteMixin, SchoolScopedViewSet):
    queryset = Room.objects.all()
    serializer_class = RoomSerializer


class PeriodViewSet(AdminWriteMixin, SchoolScopedViewSet):
    queryset = Period.objects.all()
    serializer_class = PeriodSerializer

    @action(detail=False, methods=["post"], url_path="seed-standard")
    def seed_standard(self, request):
        """Load the standard school day: 2 lessons 07:30-09:00, break,
        2 lessons 09:30-11:00, break, 2 lessons 11:30-13:00, lunch,
        3 lessons 14:00-16:00. Preps (16:00-17:00) is not a lesson slot."""
        self._require_admin_write()
        from .generator import seed_standard_day

        created = seed_standard_day(request.user.school)
        return Response({
            "created": created,
            "periods": PeriodSerializer(
                Period.objects.filter(school=request.user.school), many=True
            ).data,
        })


class LessonViewSet(AdminWriteMixin, SchoolScopedViewSet):
    queryset = Lesson.objects.select_related("period", "teacher", "learning_area", "room").all()
    serializer_class = LessonSerializer
    filterset_fields = ["day", "period", "teacher", "grade", "stream", "room"]


class LessonRequirementViewSet(SchoolScopedViewSet):
    """Teaching assignments: teacher × learning area × class. Written by the
    people who run the school day — the admin, head teacher or deputy — since
    assigning who teaches what is the head teacher's job, not only the office's."""

    queryset = LessonRequirement.objects.select_related("teacher", "learning_area").all()
    serializer_class = LessonRequirementSerializer
    filterset_fields = ["teacher", "learning_area", "grade", "stream"]

    def _require_leadership(self):
        from apps.teachers.daily import _require_office

        _require_office(self.request.user)

    def _check_phase(self, serializer):
        """A phased teacher stays in their section: Junior School staff do not
        teach primary classes, and vice versa."""
        from rest_framework.exceptions import ValidationError

        teacher = serializer.validated_data.get("teacher") or getattr(
            serializer.instance, "teacher", None
        )
        grade = serializer.validated_data.get("grade", getattr(
            serializer.instance, "grade", None
        ))
        if teacher is None or grade is None:
            return
        if not teacher.may_teach_grade(grade):
            name = teacher.user.get_full_name() or teacher.user.username
            message = (
                f"{name} is {teacher.get_phase_display()} staff and cannot be "
                f"assigned to this grade. Change their phase on the Staff page "
                f"if this is wrong."
            )
            raise ValidationError({"teacher": [message]})

    def perform_create(self, serializer):
        self._require_leadership()
        self._check_phase(serializer)
        super().perform_create(serializer)

    def perform_update(self, serializer):
        self._require_leadership()
        self._check_phase(serializer)
        serializer.save()

    def perform_destroy(self, instance):
        self._require_leadership()
        instance.delete()


class AutoAssignView(APIView):
    """POST /api/timetable/assignments/auto/ — build the G4-G9 assignments
    from teacher subjects, phases and the grades' learning areas. Leadership
    only, like hand-made assignments."""

    def post(self, request):
        from apps.teachers.daily import _require_office

        _require_office(request.user)
        from .generator import auto_assign

        return Response(auto_assign(request.user.school))


class GenerateTimetableView(APIView):
    """Regenerate the school's timetable from its LessonRequirements.
    Replaces existing lessons unless {"clear_existing": false} is passed."""

    def post(self, request):
        user = request.user
        if not (user.is_superuser or user.role == "ADMIN"):
            raise PermissionDenied(
                "Regenerating the timetable replaces every lesson — admin only."
            )
        clear = request.data.get("clear_existing", True)
        result = generate_timetable(user.school, clear_existing=bool(clear))
        return Response(result)
