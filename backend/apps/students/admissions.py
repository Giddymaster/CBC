"""Admitting a new learner.

One endpoint takes the whole admission form — the child, their guardians and
their emergency contact — and writes it in a single transaction, so a half-
finished admission never reaches the register.

Admitting is an admin power by default. The admin can delegate it to a staff
member (head teacher, deputy, a class teacher running the Grade 1 intake)
without giving away the rest of the admin portal.
"""

import re

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.views import SchoolScopedViewSet

from .models import AdmissionRight, Guardian, Learner, can_admit
from .serializers import LearnerSerializer


def next_admission_number(school, prefix="ADM"):
    """Continue the school's own numbering rather than imposing a scheme.

    Looks at the numeric tail of existing admission numbers and adds one, so
    ADM0281 -> ADM0282 and 2026/014 -> 2026/015 both behave sensibly.
    """
    numbers = []
    width = 0
    for value in Learner.objects.filter(school=school).values_list(
        "admission_number", flat=True
    ):
        match = re.search(r"(\d+)\s*$", value or "")
        if match:
            numbers.append(int(match.group(1)))
            width = max(width, len(match.group(1)))
    if not numbers:
        return f"{prefix}001"

    latest = max(numbers)
    sample = (
        Learner.objects.filter(school=school, admission_number__endswith=str(latest))
        .values_list("admission_number", flat=True)
        .first()
    )
    stem = re.sub(r"(\d+)\s*$", "", sample or prefix)
    return f"{stem}{latest + 1:0{max(width, 1)}d}"


class AdmissionGuardianSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=15)
    alt_phone = serializers.CharField(max_length=15, allow_blank=True, required=False)
    email = serializers.EmailField(allow_blank=True, required=False)
    relationship = serializers.CharField(max_length=30, allow_blank=True, required=False)
    national_id = serializers.CharField(max_length=20, allow_blank=True, required=False)
    occupation = serializers.CharField(max_length=100, allow_blank=True, required=False)
    address = serializers.CharField(max_length=200, allow_blank=True, required=False)
    is_primary_contact = serializers.BooleanField(required=False, default=False)


# Everything on the Learner an admission form may set. Kept as an explicit list
# so a new model field is a deliberate addition to the form, not an accident.
ADMISSION_FIELDS = [
    "upi", "admission_number", "first_name", "middle_name", "last_name",
    "date_of_birth", "gender", "grade", "stream", "pathway",
    "birth_certificate_no", "nationality", "religion", "admission_date",
    "previous_school", "previous_grade", "transfer_reason",
    "county", "subcounty", "ward", "home_address", "residence", "transport",
    "bus_route", "blood_group", "allergies", "chronic_conditions", "medication",
    "nhif_number", "immunisation_up_to_date", "special_needs",
    "emergency_contact_name", "emergency_contact_phone",
    "emergency_contact_relationship", "admission_notes", "extra",
]


class AdmissionSerializer(serializers.ModelSerializer):
    guardians = AdmissionGuardianSerializer(many=True, required=False)

    class Meta:
        model = Learner
        fields = ADMISSION_FIELDS + ["guardians"]
        extra_kwargs = {
            # Blank means "give the child the next number in our sequence".
            "admission_number": {"required": False, "allow_blank": True},
        }

    def validate_guardians(self, value):
        if len(value) > 4:
            raise serializers.ValidationError("At most four guardians per learner.")
        return value


class AdmissionView(APIView):
    """POST /api/admissions/ — admit one learner with their guardians."""

    def post(self, request):
        user = request.user
        if not can_admit(user):
            raise PermissionDenied(
                "You do not have admission rights. Ask the school admin to delegate them."
            )
        school = user.school
        if school is None:
            raise PermissionDenied("This account is not attached to a school.")

        serializer = AdmissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        guardians = data.pop("guardians", [])

        admission_number = (data.get("admission_number") or "").strip()
        if not admission_number:
            admission_number = next_admission_number(school)
        elif Learner.objects.filter(
            school=school, admission_number__iexact=admission_number
        ).exists():
            raise serializers.ValidationError(
                {"admission_number": f"{admission_number} is already in use at this school."}
            )
        data["admission_number"] = admission_number
        data.setdefault("admission_date", timezone.localdate())

        with transaction.atomic():
            learner = Learner.objects.create(school=school, admitted_by=user, **data)
            for row in guardians:
                if not row.get("full_name"):
                    continue
                # Reuse an existing guardian when a sibling is already enrolled,
                # so one family is one contact record.
                guardian = Guardian.objects.filter(
                    school=school, phone=row["phone"], full_name__iexact=row["full_name"]
                ).first()
                if guardian is None:
                    guardian = Guardian.objects.create(school=school, **row)
                learner.guardians.add(guardian)

        return Response(
            LearnerSerializer(learner, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class LearnerPhotoView(APIView):
    """POST/DELETE /api/learners/<id>/photo/ — the child's profile picture."""

    parser_classes = [MultiPartParser, FormParser]

    def _learner(self, request, learner_id):
        learner = Learner.objects.filter(
            school=request.user.school, pk=learner_id
        ).first()
        if learner is None:
            raise PermissionDenied("Learner not found at this school.")
        if not can_admit(request.user):
            raise PermissionDenied("You do not have rights to change learner records.")
        return learner

    def post(self, request, learner_id):
        learner = self._learner(request, learner_id)
        photo = request.FILES.get("photo")
        if photo is None:
            return Response({"detail": "Attach a photo."}, status=status.HTTP_400_BAD_REQUEST)
        learner.photo = photo
        learner.save(update_fields=["photo", "updated_at"])
        return Response({"photo": request.build_absolute_uri(learner.photo.url)})

    def delete(self, request, learner_id):
        learner = self._learner(request, learner_id)
        learner.photo = None
        learner.save(update_fields=["photo", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdmissionRightSerializer(serializers.ModelSerializer):
    staff_name = serializers.CharField(source="user.get_full_name", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    granted_by_name = serializers.CharField(
        source="granted_by.get_full_name", read_only=True, default=None
    )
    current = serializers.SerializerMethodField()

    class Meta:
        model = AdmissionRight
        fields = "__all__"
        read_only_fields = ["school", "granted_by"]

    def get_current(self, obj):
        return obj.is_current()


class AdmissionRightViewSet(SchoolScopedViewSet):
    """Admin-only: who, besides the admin, may admit learners."""

    queryset = AdmissionRight.objects.select_related("user", "granted_by").all()
    serializer_class = AdmissionRightSerializer
    filterset_fields = ["active", "user"]

    def _require_admin(self):
        user = self.request.user
        if not (user.is_superuser or user.role == "ADMIN"):
            raise PermissionDenied("Only the school admin can delegate admission rights.")

    def _check_staff(self, serializer):
        """The grantee must be a staff login of this school — not a parent, and
        not somebody from another school."""
        from apps.teachers.models import SupportStaff, Teacher

        target = serializer.validated_data.get("user")
        if target is None:
            return
        school = self.request.user.school
        is_staff = (
            Teacher.objects.filter(user=target, school=school).exists()
            or SupportStaff.objects.filter(user=target, school=school).exists()
        )
        if not is_staff:
            raise serializers.ValidationError(
                {"user": "Choose a staff member of this school."}
            )

    def perform_create(self, serializer):
        self._require_admin()
        self._check_staff(serializer)
        serializer.save(school=self.request.user.school, granted_by=self.request.user)

    def perform_update(self, serializer):
        self._require_admin()
        self._check_staff(serializer)
        serializer.save()

    def perform_destroy(self, instance):
        # Keep the record of who once held the right; just switch it off.
        self._require_admin()
        instance.active = False
        instance.save(update_fields=["active", "updated_at"])


class MyAdmissionAccessView(APIView):
    """GET /api/admissions/access/ — may I admit, and under what grant?"""

    def get(self, request):
        user = request.user
        right = (
            AdmissionRight.objects.filter(school=user.school, user=user).first()
            if user.school_id
            else None
        )
        is_admin = user.is_superuser or user.role == "ADMIN"
        return Response(
            {
                "can_admit": can_admit(user),
                "reason": "School admin" if is_admin else (
                    "Delegated by the school admin" if right and right.is_current() else None
                ),
                "note": right.note if right else "",
                "expires_on": right.expires_on if right else None,
                "next_admission_number": (
                    next_admission_number(user.school) if can_admit(user) and user.school else None
                ),
            }
        )
