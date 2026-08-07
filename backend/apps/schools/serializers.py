from rest_framework import serializers

from .models import School


class SchoolSerializer(serializers.ModelSerializer):
    class Meta:
        model = School
        fields = "__all__"

    def validate_levels(self, value):
        return School.normalize_levels(value)
