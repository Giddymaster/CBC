from rest_framework import serializers

from .models import Facility, FacilityAssignment, FacilityCategory, NavSection, Supply


class NavSectionSerializer(serializers.ModelSerializer):
    categories = serializers.SerializerMethodField()

    class Meta:
        model = NavSection
        fields = "__all__"
        read_only_fields = ["school"]

    def get_categories(self, obj):
        return [
            {"id": c.id, "name": c.name, "facility_count": c.facilities.count()}
            for c in obj.categories.all()
        ]


class FacilityCategorySerializer(serializers.ModelSerializer):
    facility_count = serializers.SerializerMethodField()

    class Meta:
        model = FacilityCategory
        fields = "__all__"
        read_only_fields = ["school"]

    def get_facility_count(self, obj):
        return obj.facilities.count()


class SupplySerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)

    class Meta:
        model = Supply
        fields = "__all__"
        read_only_fields = ["school"]


class FacilityAssignmentSerializer(serializers.ModelSerializer):
    staff_name = serializers.CharField(read_only=True)
    staff_kind = serializers.SerializerMethodField()

    class Meta:
        model = FacilityAssignment
        fields = "__all__"
        read_only_fields = ["school"]

    def get_staff_kind(self, obj):
        return "TEACHING" if obj.teacher_id else "NON_TEACHING"

    def validate(self, data):
        teacher = data.get("teacher", getattr(self.instance, "teacher", None))
        support = data.get("support_staff", getattr(self.instance, "support_staff", None))
        if bool(teacher) == bool(support):
            raise serializers.ValidationError(
                "Pick exactly one staff member — either teaching or non-teaching."
            )
        return data


class FacilitySerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    staff_count = serializers.SerializerMethodField()
    supply_summary = serializers.SerializerMethodField()

    class Meta:
        model = Facility
        fields = "__all__"
        read_only_fields = ["school"]

    def get_staff_count(self, obj):
        return obj.assignments.count()

    def get_supply_summary(self, obj):
        counts = {"total": 0, "in_stock": 0, "low": 0, "depleted": 0}
        for supply in obj.supplies.all():
            counts["total"] += 1
            counts[supply.status.lower()] += 1
        return counts


class FacilityDetailSerializer(FacilitySerializer):
    """Facility plus everything it holds — who works there and what's in store."""

    assignments = FacilityAssignmentSerializer(many=True, read_only=True)
    supplies = SupplySerializer(many=True, read_only=True)
