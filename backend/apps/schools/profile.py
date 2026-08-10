"""The school's own record of itself.

Everything on this page is a thing the school, not the platform operator, gets
to say: the number a parent rings, the badge at the top of a report card, the
headings on the fee note, the certificate an inspector asks for. The operator
console holds the school's *registration* — its MoE code, county and billing
plan — and that stays there, because a school renaming its own code would break
the register it is registered in.
"""

from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.images import downscale_photo
from apps.common.views import SchoolScopedViewSet

from .models import DEFAULT_VOTE_HEADS, SchoolDocument
from .serializers import SchoolDocumentSerializer, SchoolProfileSerializer


def can_edit_profile(user):
    """The office and the school's leadership.

    The head teacher and deputy run the school; the crest, the motto and the
    office number are theirs to set as much as the administrator's, and in a
    small school they are often the only ones who would know the postal box.
    Every other member of staff reads the page — the office number belongs on
    a screen they can reach.
    """
    from apps.payments.access import is_office, is_school_leadership

    return is_office(user) or is_school_leadership(user)

# What a school may change about itself. An allowlist rather than the whole
# model: `code` identifies the school to the Ministry and
# `paybill_account_prefix` steers how M-Pesa payments match invoices, so both
# stay with the operator.
EDITABLE = [
    "contact_phone", "alt_phone", "contact_email", "postal_address",
    "website", "motto", "vote_heads",
]


class MySchoolProfileView(APIView):
    """GET/PATCH /api/my-school/profile/ — read by any member of staff (the
    office number belongs on every screen), written only by the school admin."""

    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def _school(self):
        school = getattr(self.request.user, "school", None)
        if school is None:
            raise PermissionDenied("This account is not attached to a school.")
        return school

    def get(self, request):
        school = self._school()
        return Response(
            {
                **SchoolProfileSerializer(school, context={"request": request}).data,
                "can_edit": can_edit_profile(request.user),
                "default_vote_heads": DEFAULT_VOTE_HEADS,
                "document_categories": [
                    {"value": value, "label": label}
                    for value, label in SchoolDocument.Category.choices
                ],
            }
        )

    def patch(self, request):
        school = self._school()
        if not can_edit_profile(request.user):
            raise PermissionDenied(
                "The school's details are set by the office or the head teacher."
            )

        data = {key: value for key, value in request.data.items() if key in EDITABLE}
        if "vote_heads" in data:
            data["vote_heads"] = _clean_vote_heads(data["vote_heads"])

        serializer = SchoolProfileSerializer(
            school, data=data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        # The badge comes up the same request as a file, so it is handled apart
        # from the serialised fields. Sent empty, it clears — a school that has
        # rebranded should not be stuck with the old crest.
        if "logo" in request.FILES:
            # Not square-cropped: a school crest is rarely square and a centre
            # crop would cut the name off a wide one.
            school.logo = downscale_photo(request.FILES["logo"], max_edge=600, square=False)
            school.save(update_fields=["logo"])
        elif request.data.get("logo") in ("", "null", None) and "logo" in request.data:
            school.logo = None
            school.save(update_fields=["logo"])

        school.refresh_from_db()
        return Response(SchoolProfileSerializer(school, context={"request": request}).data)


def _clean_vote_heads(value):
    """Headings the school typed, tidied: blanks dropped, duplicates collapsed,
    order kept — the fee note reads left to right in the order given."""
    if isinstance(value, str):
        # A multipart form cannot send a list, so it arrives comma-separated.
        value = value.split(",")
    if not isinstance(value, list):
        raise ValidationError({"vote_heads": ["Send a list of headings."]})
    cleaned = []
    for head in value:
        text = str(head).strip()
        if text and text.lower() not in {h.lower() for h in cleaned}:
            cleaned.append(text)
    return cleaned


class SchoolDocumentViewSet(SchoolScopedViewSet):
    """The school's filing cabinet. Staff read it; the office files and removes."""

    queryset = SchoolDocument.objects.all()
    serializer_class = SchoolDocumentSerializer
    filterset_fields = ["category"]
    search_fields = ["title", "note"]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def _require_admin(self):
        if not can_edit_profile(self.request.user):
            raise PermissionDenied(
                "Documents are filed by the office or the head teacher."
            )

    def perform_create(self, serializer):
        self._require_admin()
        serializer.save(school=self.request.user.school, uploaded_by=self.request.user)

    def perform_update(self, serializer):
        self._require_admin()
        serializer.save()

    def perform_destroy(self, instance):
        self._require_admin()
        instance.delete()


def school_letterhead(school, request=None):
    """The school as it should head a printed page, in one dict.

    Report cards, fee notes and admission forms all want the same few lines, and
    all three used to build them separately — so a school that filled in its
    postal address saw it appear on one and not the others.
    """
    logo = logo_path = None
    if school.logo:
        try:
            logo = (
                request.build_absolute_uri(school.logo.url) if request else school.logo.url
            )
            # The PDF renderer draws from disk, not over HTTP.
            logo_path = school.logo.path
        except (ValueError, NotImplementedError):
            logo = logo_path = None
    contacts = [c for c in [school.contact_phone, school.alt_phone] if c]
    return {
        "name": school.name,
        "code": school.code,
        "county": school.county,
        "motto": school.motto,
        "logo": logo,
        "logo_path": logo_path,
        "phone": " / ".join(contacts),
        "email": school.contact_email,
        "address": school.postal_address,
        "website": school.website,
    }
