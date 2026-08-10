from rest_framework import serializers

from .models import Announcement, MessageBlast, SmsMessage


class SmsMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SmsMessage
        fields = "__all__"
        read_only_fields = ["school", "status", "provider_message_id", "error"]


class MessageBlastSerializer(serializers.ModelSerializer):
    sent_by_name = serializers.SerializerMethodField()
    delivery = serializers.SerializerMethodField()

    class Meta:
        model = MessageBlast
        fields = "__all__"
        read_only_fields = ["school", "recipients", "sent_by"]

    def get_sent_by_name(self, blast):
        user = blast.sent_by
        if user is None:
            return ""
        return user.get_full_name() or user.username

    def get_delivery(self, blast):
        """What actually happened, counted by status — the school's receipt."""
        counts = {}
        for status in blast.messages.values_list("status", flat=True):
            counts[status] = counts.get(status, 0) + 1
        return counts

    def validate(self, attrs):
        audience = attrs.get("audience", getattr(self.instance, "audience", None))
        if audience == MessageBlast.Audience.GRADE and attrs.get("grade") is None:
            raise serializers.ValidationError({"grade": ["Choose the class to message."]})
        if audience == MessageBlast.Audience.LEARNER and not attrs.get("learner"):
            raise serializers.ValidationError({"learner": ["Choose the learner."]})
        if not (attrs.get("body") or "").strip():
            raise serializers.ValidationError({"body": ["Write the message first."]})
        return attrs


class AnnouncementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Announcement
        fields = "__all__"
        read_only_fields = ["school"]
