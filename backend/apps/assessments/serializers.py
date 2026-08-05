from rest_framework import serializers

from .models import Assessment, LearningArea, Score


class LearningAreaSerializer(serializers.ModelSerializer):
    class Meta:
        model = LearningArea
        fields = "__all__"


class AssessmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Assessment
        fields = "__all__"
        read_only_fields = ["school"]


class ScoreSerializer(serializers.ModelSerializer):
    competency_level = serializers.CharField(read_only=True)
    learner_name = serializers.CharField(source="learner.full_name", read_only=True)

    class Meta:
        model = Score
        fields = "__all__"
        read_only_fields = ["school"]

    def validate(self, data):
        assessment = data.get("assessment") or getattr(self.instance, "assessment", None)
        marks = data.get("marks")
        if assessment and marks is not None and marks > assessment.max_marks:
            raise serializers.ValidationError(
                {"marks": f"Marks exceed max_marks ({assessment.max_marks})."}
            )
        return data
