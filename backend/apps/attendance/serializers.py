from rest_framework import serializers

from .models import AttendanceRecord


class AttendanceRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttendanceRecord
        fields = "__all__"
        read_only_fields = ["school"]


class BulkAttendanceSerializer(serializers.Serializer):
    """One class register in one request — the whole day syncs in one retryable unit."""

    date = serializers.DateField()
    records = serializers.ListField(
        child=serializers.DictField(), help_text='[{"learner": id, "status": "P|A|L|E"}, ...]'
    )
