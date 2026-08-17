from django.db.models import Count
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.common.audit import record as audit
from apps.common.media import signed_media_url
from apps.common.views import AdminWriteMixin, SchoolScopedViewSet, is_staff_member

from .models import ClassGroup, Guardian, Learner, LearnerField, Pathway
from .serializers import (
    ClassGroupSerializer,
    GuardianContactSerializer,
    GuardianSerializer,
    LearnerFieldSerializer,
    LearnerSerializer,
    PathwaySerializer,
)


class LearnerFieldViewSet(SchoolScopedViewSet):
    """Admin-defined extra columns on the learner register."""

    queryset = LearnerField.objects.all()
    serializer_class = LearnerFieldSerializer

    def _require_admin(self):
        user = self.request.user
        if not (user.is_superuser or user.role == "ADMIN"):
            raise PermissionDenied("Only the school admin can change learner columns.")

    def perform_create(self, serializer):
        self._require_admin()
        super().perform_create(serializer)

    def perform_update(self, serializer):
        self._require_admin()
        serializer.save()

    def perform_destroy(self, instance):
        self._require_admin()
        instance.delete()


class ClassGroupViewSet(SchoolScopedViewSet):
    """Classes (grade + stream) and their class teacher. Seating a class
    teacher is school leadership's job — the office, the head teacher or the
    deputy — not only the office's."""

    queryset = ClassGroup.objects.select_related("class_teacher__user").all()
    serializer_class = ClassGroupSerializer
    filterset_fields = ["grade", "stream", "class_teacher"]

    def _require_leadership(self):
        from apps.teachers.daily import _require_office

        _require_office(self.request.user)

    def perform_create(self, serializer):
        self._require_leadership()
        super().perform_create(serializer)

    def perform_update(self, serializer):
        self._require_leadership()
        serializer.save()

    def perform_destroy(self, instance):
        self._require_leadership()
        instance.delete()


class PathwayViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    """The three MoE pathways. National; there is rarely a reason to touch
    them at all outside seeding, so writes are admin-only and deletes are
    for the platform."""

    queryset = Pathway.objects.all()
    serializer_class = PathwaySerializer

    def perform_destroy(self, instance):
        if not self.request.user.is_superuser:
            raise PermissionDenied(
                "Pathways are national — platform administrators only."
            )
        instance.delete()


class GuardianViewSet(SchoolScopedViewSet):
    """The guardian register is every family's name and phone number.

    School scoping alone is not enough here, because parents are
    school-scoped users too — without a role check a parent could list
    every other family's contact details. Staff read; the admin writes."""

    queryset = Guardian.objects.all()
    serializer_class = GuardianSerializer
    search_fields = ["full_name", "phone"]

    def get_queryset(self):
        if not is_staff_member(self.request.user):
            raise PermissionDenied("The guardian register is staff-only.")
        return super().get_queryset()

    def perform_create(self, serializer):
        self._require_admin()
        super().perform_create(serializer)

    def perform_update(self, serializer):
        self._require_admin()
        serializer.save()

    def perform_destroy(self, instance):
        self._require_admin()
        instance.delete()

    def _require_admin(self):
        user = self.request.user
        if not (user.is_superuser or user.role == "ADMIN"):
            raise PermissionDenied("Only the school admin can change guardian records.")


class LearnerViewSet(SchoolScopedViewSet):
    queryset = Learner.objects.select_related("pathway").prefetch_related("guardians").all()
    serializer_class = LearnerSerializer
    # admission_number is exact-matchable so the fees desk can look a family
    # up by the number the parent quotes.
    filterset_fields = [
        "grade", "stream", "pathway", "gender", "active", "admission_number",
    ]
    search_fields = ["first_name", "middle_name", "last_name", "admission_number", "upi"]

    def get_queryset(self):
        # A parent may reach their own children (the profile action needs it),
        # but must not page the whole school's roll — that list is the id
        # source for every other per-learner endpoint.
        qs = super().get_queryset()
        user = self.request.user
        if is_staff_member(user):
            return qs
        guardian = getattr(user, "guardian_profile", None)
        if guardian is not None:
            return qs.filter(pk__in=guardian.learners.values("pk"))
        return qs.none()

    def _require_admin(self):
        user = self.request.user
        if not (user.is_superuser or user.role == "ADMIN"):
            raise PermissionDenied("Only the school admin can change learner records.")

    def perform_create(self, serializer):
        self._require_admin()
        super().perform_create(serializer)

    def perform_update(self, serializer):
        self._require_admin()
        was_active = serializer.instance.active
        learner = serializer.save()
        if was_active != learner.active:
            audit(
                actor=self.request.user,
                school=learner.school,
                action=("LEARNER_REACTIVATED" if learner.active else "LEARNER_DEACTIVATED"),
                target=learner,
                label=f"{learner.full_name} ({learner.admission_number})",
            )

    def perform_destroy(self, instance):
        # Learner records are kept for history — deactivate instead of deleting.
        self._require_admin()
        instance.active = False
        instance.save(update_fields=["active", "updated_at"])
        audit(
            actor=self.request.user,
            school=instance.school,
            action="LEARNER_DEACTIVATED",
            target=instance,
            label=f"{instance.full_name} ({instance.admission_number})",
        )

    @action(detail=True)
    def profile(self, request, pk=None):
        """Full student profile: scores, guardians, fees, attendance."""
        learner = self.get_object()
        user = request.user
        if getattr(user, "role", None) == "PARENT":
            guardian = getattr(user, "guardian_profile", None)
            if guardian is None or not guardian.learners.filter(pk=learner.pk).exists():
                raise PermissionDenied("You can only view your own children.")

        from apps.assessments.reports import build_report_card
        from apps.attendance.models import AttendanceRecord
        from apps.payments.models import Invoice

        year = int(request.query_params.get("year", timezone.now().year))
        report = build_report_card(learner, year=year)

        invoices = list(Invoice.objects.filter(learner=learner).select_related("fee_structure"))
        balance = sum((inv.balance for inv in invoices), start=0)

        counts = {
            row["status"]: row["n"]
            for row in AttendanceRecord.objects.filter(learner=learner)
            .values("status")
            .annotate(n=Count("id"))
        }
        recent = [
            {"date": a.date.isoformat(), "status": a.status}
            for a in AttendanceRecord.objects.filter(learner=learner).order_by("-date")[:10]
        ]

        is_staff = user.is_superuser or getattr(user, "role", None) in ("ADMIN", "TEACHER", "SUPPORT")
        return Response(
            {
                "report_card": report,
                "photo": signed_media_url(request, learner.photo),
                # The admission record: identity, home, health and next of kin.
                # Health and address detail is the school's duty-of-care data,
                # so it is staff-only — a parent gets the rest.
                "admission": {
                    "admission_number": learner.admission_number,
                    "upi": learner.upi,
                    "date_of_birth": learner.date_of_birth,
                    "gender": learner.get_gender_display(),
                    "admission_date": learner.admission_date,
                    "admitted_by": (
                        learner.admitted_by.get_full_name() if learner.admitted_by else None
                    ),
                    "nationality": learner.nationality,
                    "religion": learner.religion,
                    "residence": learner.get_residence_display(),
                    "transport": learner.get_transport_display(),
                    "bus_route": learner.bus_route,
                    "previous_school": learner.previous_school,
                    **(
                        {
                            "birth_certificate_no": learner.birth_certificate_no,
                            "county": learner.county,
                            "subcounty": learner.subcounty,
                            "ward": learner.ward,
                            "home_address": learner.home_address,
                            "blood_group": learner.blood_group,
                            "allergies": learner.allergies,
                            "chronic_conditions": learner.chronic_conditions,
                            "medication": learner.medication,
                            "nhif_number": learner.nhif_number,
                            "immunisation_up_to_date": learner.immunisation_up_to_date,
                            "special_needs": learner.special_needs,
                            "emergency_contact_name": learner.emergency_contact_name,
                            "emergency_contact_phone": learner.emergency_contact_phone,
                            "emergency_contact_relationship": (
                                learner.emergency_contact_relationship
                            ),
                            "admission_notes": learner.admission_notes,
                        }
                        if is_staff
                        else {}
                    ),
                },
                "guardians": GuardianContactSerializer(learner.guardians.all(), many=True).data,
                "fees": {
                    "total_balance": str(balance),
                    "invoices": [
                        {
                            "id": inv.id,
                            "description": str(inv.fee_structure),
                            "due": str(inv.amount_due),
                            "paid": str(inv.amount_paid),
                            "balance": str(inv.balance),
                            "status": inv.status,
                        }
                        for inv in invoices
                    ],
                },
                "attendance": {
                    "present": counts.get("P", 0),
                    "absent": counts.get("A", 0),
                    "late": counts.get("L", 0),
                    "excused": counts.get("E", 0),
                    "recent": recent,
                },
            }
        )
