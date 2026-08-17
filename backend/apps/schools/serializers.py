from rest_framework import serializers

from apps.common.media import signed_media_url
from apps.common.uploads import validate_document

from .models import School, SchoolDocument


class SchoolSerializer(serializers.ModelSerializer):
    class Meta:
        model = School
        fields = "__all__"

    def validate_levels(self, value):
        return School.normalize_levels(value)


class SchoolProfileSerializer(serializers.ModelSerializer):
    """The school as it describes itself. Registration facts are readable but
    not writable here — see the EDITABLE allowlist in profile.py."""

    logo_url = serializers.SerializerMethodField()
    fee_columns = serializers.SerializerMethodField()

    class Meta:
        model = School
        fields = [
            "id", "name", "code", "kemis_code", "levels", "county", "subcounty",
            "ward", "zone", "category", "gender", "accommodation", "ownership",
            "contact_phone", "alt_phone", "contact_email", "postal_address",
            "website", "motto", "logo_url", "vote_heads", "fee_columns",
            "paybill_account_prefix",
        ]
        read_only_fields = [
            "name", "code", "kemis_code", "levels", "county", "subcounty", "ward",
            "zone", "category", "gender", "accommodation", "ownership",
            "paybill_account_prefix",
        ]

    def get_logo_url(self, school):
        return signed_media_url(self.context.get("request"), school.logo)

    def get_fee_columns(self, school):
        return school.fee_columns()


class SchoolDocumentSerializer(serializers.ModelSerializer):
    file = serializers.FileField(validators=[validate_document])
    file_url = serializers.SerializerMethodField()
    uploaded_by_name = serializers.SerializerMethodField()
    category_label = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = SchoolDocument
        fields = "__all__"
        read_only_fields = ["school", "uploaded_by"]

    def get_file_url(self, document):
        return signed_media_url(self.context.get("request"), document.file)

    def get_uploaded_by_name(self, document):
        user = document.uploaded_by
        if user is None:
            return ""
        return user.get_full_name() or user.username
