from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.views import SchoolScopedViewSet

from .generator import generate_timetable
from .models import Lesson, LessonRequirement, Period, Room
from .serializers import (
    LessonRequirementSerializer,
    LessonSerializer,
    PeriodSerializer,
    RoomSerializer,
)


class RoomViewSet(SchoolScopedViewSet):
    queryset = Room.objects.all()
    serializer_class = RoomSerializer


class PeriodViewSet(SchoolScopedViewSet):
    queryset = Period.objects.all()
    serializer_class = PeriodSerializer


class LessonViewSet(SchoolScopedViewSet):
    queryset = Lesson.objects.select_related("period", "teacher", "learning_area", "room").all()
    serializer_class = LessonSerializer
    filterset_fields = ["day", "period", "teacher", "grade", "stream", "room"]


class LessonRequirementViewSet(SchoolScopedViewSet):
    queryset = LessonRequirement.objects.select_related("teacher", "learning_area").all()
    serializer_class = LessonRequirementSerializer
    filterset_fields = ["teacher", "learning_area", "grade", "stream"]


class GenerateTimetableView(APIView):
    """Regenerate the school's timetable from its LessonRequirements.
    Replaces existing lessons unless {"clear_existing": false} is passed."""

    def post(self, request):
        clear = request.data.get("clear_existing", True)
        result = generate_timetable(request.user.school, clear_existing=bool(clear))
        return Response(result)
