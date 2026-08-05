from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Lesson, LessonRequirement, Period, Room


class LessonRequirementSerializer(serializers.ModelSerializer):
    class Meta:
        model = LessonRequirement
        fields = "__all__"
        read_only_fields = ["school"]


class RoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = "__all__"
        read_only_fields = ["school"]


class PeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = Period
        fields = "__all__"
        read_only_fields = ["school"]


class LessonSerializer(serializers.ModelSerializer):
    learning_area_name = serializers.CharField(source="learning_area.name", read_only=True)
    teacher_name = serializers.CharField(source="teacher.user.get_full_name", read_only=True)

    class Meta:
        model = Lesson
        fields = "__all__"
        read_only_fields = ["school"]

    def validate(self, data):
        # Run model clash detection with the school the row will actually get.
        instance = Lesson(**{**data, "school": self.context["request"].user.school})
        if self.instance:
            instance.pk = self.instance.pk
        try:
            instance.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict)
        return data
