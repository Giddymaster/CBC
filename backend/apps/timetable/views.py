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


class LessonViewSet(AdminWriteMixin, SchoolScopedViewSet):
    queryset = Lesson.objects.select_related("period", "teacher", "learning_area", "room").all()
    serializer_class = LessonSerializer
    filterset_fields = ["day", "period", "teacher", "grade", "stream", "room"]


class LessonRequirementViewSet(AdminWriteMixin, SchoolScopedViewSet):
    queryset = LessonRequirement.objects.select_related("teacher", "learning_area").all()
    serializer_class = LessonRequirementSerializer
    filterset_fields = ["teacher", "learning_area", "grade", "stream"]


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
