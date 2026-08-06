from apps.common.views import AdminWriteMixin, SchoolScopedViewSet

from .models import Announcement, SmsMessage
from .serializers import AnnouncementSerializer, SmsMessageSerializer
from .services import send_sms
from .tasks import blast_announcement_sms


class SmsMessageViewSet(AdminWriteMixin, SchoolScopedViewSet):
    """POST creates AND sends the SMS (or stores it as STUBBED without a gateway)."""

    queryset = SmsMessage.objects.all()
    serializer_class = SmsMessageSerializer
    filterset_fields = ["status", "recipient"]
    http_method_names = ["get", "post", "head", "options"]

    def perform_create(self, serializer):
        # Overriding perform_create skips the mixin's guard, so it is called
        # explicitly — an open POST here is a free SMS gateway.
        self._require_admin_write()
        data = serializer.validated_data
        message = send_sms(self.request.user.school, data["recipient"], data["body"])
        serializer.instance = message


class AnnouncementViewSet(AdminWriteMixin, SchoolScopedViewSet):
    queryset = Announcement.objects.all()
    serializer_class = AnnouncementSerializer
    filterset_fields = ["audience"]

    def perform_create(self, serializer):
        super().perform_create(serializer)
        if serializer.instance.send_sms:
            blast_announcement_sms.delay(serializer.instance.pk)
