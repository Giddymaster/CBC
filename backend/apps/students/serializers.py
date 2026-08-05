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
        fields = [
            "id", "full_name", "phone", "alt_phone", "email", "relationship",
            "national_id", "occupation", "address", "is_primary_contact",
        ]


class LearnerSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    pathway_display = serializers.CharField(source="pathway.get_code_display", read_only=True, default=None)
    guardians_detail = GuardianContactSerializer(source="guardians", many=True, read_only=True)
    admitted_by_name = serializers.CharField(
        source="admitted_by.get_full_name", read_only=True, default=None
    )
    residence_label = serializers.CharField(source="get_residence_display", read_only=True)
    transport_label = serializers.CharField(source="get_transport_display", read_only=True)

    class Meta:
        model = Learner
        fields = "__all__"
        read_only_fields = ["school", "photo", "admitted_by"]

    # Medical and next-of-kin detail is held for the school's duty of care, not
    # for general circulation. Only staff see it.
    SENSITIVE = [
        "guardians_detail", "blood_group", "allergies", "chronic_conditions",
        "medication", "nhif_number", "special_needs", "birth_certificate_no",
        "home_address", "emergency_contact_name", "emergency_contact_phone",
        "emergency_contact_relationship", "admission_notes", "transfer_reason",
    ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if request is not None and getattr(request.user, "role", None) == "PARENT":
            for field in self.SENSITIVE:
                data.pop(field, None)
        return data
