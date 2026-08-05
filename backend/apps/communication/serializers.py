from rest_framework import serializers

from .models import Announcement, SmsMessage


class SmsMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SmsMessage
        fields = "__all__"
        read_only_fields = ["school", "status", "provider_message_id", "error"]


class AnnouncementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Announcement
        fields = "__all__"
        read_only_fields = ["school"]
