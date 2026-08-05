from rest_framework import serializers

from .models import ClassGroup, Guardian, Learner, LearnerField, Pathway


class LearnerFieldSerializer(serializers.ModelSerializer):
    class Meta:
        model = LearnerField
        fields = "__all__"
        read_only_fields = ["school", "key"]

    def create(self, validated_data):
        # Derive a stable key from the label so renaming keeps stored values.
        from django.utils.text import slugify

        base = slugify(validated_data["label"]).replace("-", "_") or "field"
        key, n = base, 1
        school = validated_data["school"]
        while LearnerField.objects.filter(school=school, key=key).exists():
            n += 1
            key = f"{base}_{n}"
        validated_data["key"] = key
        return super().create(validated_data)


class ClassGroupSerializer(serializers.ModelSerializer):
    class_teacher_name = serializers.CharField(
        source="class_teacher.user.get_full_name", read_only=True, default=None
    )
    label = serializers.CharField(source="__str__", read_only=True)

    class Meta:
        model = ClassGroup
        fields = "__all__"
        read_only_fields = ["school"]


class PathwaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Pathway
        fields = "__all__"


class GuardianSerializer(serializers.ModelSerializer):
    class Meta:
        model = Guardian
        fields = "__all__"
        read_only_fields = ["school"]


class GuardianContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Guardian
        fields = ["id", "full_name", "phone", "email", "relationship"]


class LearnerSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    pathway_display = serializers.CharField(source="pathway.get_code_display", read_only=True, default=None)
    guardians_detail = GuardianContactSerializer(source="guardians", many=True, read_only=True)

    class Meta:
        model = Learner
        fields = "__all__"
        read_only_fields = ["school"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Guardian contacts are staff-only: parents don't get other
        # families' names and phone numbers.
        request = self.context.get("request")
        if request is not None and getattr(request.user, "role", None) == "PARENT":
            data.pop("guardians_detail", None)
        return data
