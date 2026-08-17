from rest_framework import serializers

from apps.common.media import SignedFileField
from apps.common.uploads import validate_document, validate_image

from .models import LessonPlan, SchemeOfWork, Teacher


class TeacherSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="user.get_full_name", read_only=True)
    # Writable like the plain field; only the JSON representation is signed.
    photo = SignedFileField(required=False, allow_null=True, validators=[validate_image])

    class Meta:
        model = Teacher
        fields = "__all__"
        read_only_fields = ["school"]


class SchemeOfWorkSerializer(serializers.ModelSerializer):
    document = SignedFileField(required=False, allow_null=True, validators=[validate_document])
    teacher_name = serializers.CharField(source="teacher.user.get_full_name", read_only=True)
    learning_area_name = serializers.CharField(source="learning_area.name", read_only=True)
    reviewed_by_name = serializers.CharField(
        source="reviewed_by.get_full_name", read_only=True, default=None
    )

    class Meta:
        model = SchemeOfWork
        fields = "__all__"
        read_only_fields = [
            "school", "source", "status", "reviewed_by", "reviewed_at", "review_comment",
        ]
        # Teacher users are attached automatically in the viewset.
        extra_kwargs = {"teacher": {"required": False}}


class LessonPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = LessonPlan
        fields = "__all__"
        read_only_fields = ["school"]
