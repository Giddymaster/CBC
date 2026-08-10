from django.conf import settings
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.views import AdminWriteMixin, SchoolScopedViewSet

from . import audience as audience_module
from .access import can_send_blast
from .models import Announcement, Channel, MessageBlast, SmsMessage
from .serializers import (
    AnnouncementSerializer,
    MessageBlastSerializer,
    SmsMessageSerializer,
)
from .services import send_sms
from .tasks import blast_announcement_sms, deliver_blast


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


def _segments(text):
    """How many SMS one message costs. 160 characters, or 153 each once it
    splits, because the split steals room for the join-them-up header."""
    length = len(text)
    if length <= 160:
        return 1
    return -(-length // 153)


class MessageBlastViewSet(SchoolScopedViewSet):
    """Compose once, reach a whole class or the whole school.

    ``preview`` is the important half. Every message is charged and cannot be
    unsent, so the office sees the recipient count, the message count and their
    own words as one real parent will read them — and only then presses send.
    """

    queryset = MessageBlast.objects.all()
    serializer_class = MessageBlastSerializer
    filterset_fields = ["channel", "audience"]
    http_method_names = ["get", "post", "head", "options"]

    def _guard(self):
        if not can_send_blast(self.request.user):
            raise PermissionDenied(
                "Only the office, the bursar or the head teacher may message parents."
            )

    def get_queryset(self):
        self._guard()
        return super().get_queryset().prefetch_related("messages")

    def perform_create(self, serializer):
        self._guard()
        blast = serializer.save(school=self.request.user.school, sent_by=self.request.user)
        entries = audience_module.resolve(
            blast.school,
            audience=blast.audience,
            grade=blast.grade,
            stream=blast.stream,
            learner=blast.learner,
        )
        blast.recipients = len(entries)
        blast.save(update_fields=["recipients"])
        deliver_blast.delay(blast.pk)

    @action(detail=False, methods=["post"])
    def preview(self, request):
        """Who this reaches and what it will say — before a shilling is spent."""
        self._guard()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        school = request.user.school
        entries = audience_module.resolve(
            school,
            audience=data["audience"],
            grade=data.get("grade"),
            stream=data.get("stream") or "",
            learner=data.get("learner"),
        )
        body = data["body"]
        rendered = [audience_module.render(body, entry, school) for entry in entries]
        channel = data.get("channel", Channel.SMS)
        return Response(
            {
                "recipients": len(entries),
                "segments": sum(_segments(text) for text in rendered)
                if channel == Channel.SMS
                else len(rendered),
                "live": bool(
                    settings.AT_API_KEY
                    if channel == Channel.SMS
                    else settings.WHATSAPP_TOKEN and settings.WHATSAPP_PHONE_NUMBER_ID
                ),
                # A handful of real recipients, so a wrong merge field or an
                # empty balance is caught by eye rather than by a parent.
                "sample": [
                    {
                        "name": entry["name"],
                        "phone": entry["phone"],
                        "learner": entry["learner"],
                        "class": entry["class"],
                        "text": text,
                    }
                    for entry, text in list(zip(entries, rendered))[:5]
                ],
            }
        )


class MessagingStatusView(APIView):
    """Which channels this school can actually use today.

    The UI asks before it offers WhatsApp: without the school's own Meta
    credentials a WhatsApp blast is only logged, and it is more honest to say
    so on the compose screen than to let the office believe nine hundred
    parents were told about tomorrow's meeting.
    """

    def get(self, request):
        return Response(
            {
                "may_send": can_send_blast(request.user),
                "sms": {
                    "live": bool(settings.AT_API_KEY),
                    "sender_id": settings.AT_SENDER_ID,
                },
                "whatsapp": {
                    "live": bool(
                        settings.WHATSAPP_TOKEN and settings.WHATSAPP_PHONE_NUMBER_ID
                    ),
                    "template": settings.WHATSAPP_TEMPLATE,
                },
                "merge_fields": [
                    {"field": "{name}", "means": "Parent's name"},
                    {"field": "{learner}", "means": "Their child's name"},
                    {"field": "{class}", "means": "The child's class"},
                    {"field": "{balance}", "means": "Fee balance owing"},
                    {"field": "{school}", "means": "School name"},
                ],
            }
        )


class AnnouncementViewSet(AdminWriteMixin, SchoolScopedViewSet):
    queryset = Announcement.objects.all()
    serializer_class = AnnouncementSerializer
    filterset_fields = ["audience"]

    def perform_create(self, serializer):
        super().perform_create(serializer)
        if serializer.instance.send_sms:
            blast_announcement_sms.delay(serializer.instance.pk)
