from apps.common.views import SchoolScopedViewSet

from .models import Announcement, SmsMessage
from .serializers import AnnouncementSerializer, SmsMessageSerializer
from .services import send_sms
from .tasks import blast_announcement_sms


class SmsMessageViewSet(SchoolScopedViewSet):
    """POST creates AND sends the SMS (or stores it as STUBBED without a gateway)."""

    queryset = SmsMessage.objects.all()
    serializer_class = SmsMessageSerializer
    filterset_fields = ["status", "recipient"]
    http_method_names = ["get", "post", "head", "options"]

    def perform_create(self, serializer):
        data = serializer.validated_data
        message = send_sms(self.request.user.school, data["recipient"], data["body"])
        serializer.instance = message


class AnnouncementViewSet(SchoolScopedViewSet):
    queryset = Announcement.objects.all()
    serializer_class = AnnouncementSerializer
    filterset_fields = ["audience"]

    def perform_create(self, serializer):
        super().perform_create(serializer)
        if serializer.instance.send_sms:
            blast_announcement_sms.delay(serializer.instance.pk)
