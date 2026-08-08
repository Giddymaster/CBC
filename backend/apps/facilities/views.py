from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.views import SchoolScopedViewSet

from .models import Facility, FacilityAssignment, FacilityCategory, NavSection, Supply
from .serializers import (
    FacilityAssignmentSerializer,
    FacilityCategorySerializer,
    FacilityDetailSerializer,
    FacilitySerializer,
    NavSectionSerializer,
    SupplySerializer,
)


class AdminWriteMixin:
    """Anyone on staff can look; only the admin can change."""

    def _require_admin(self):
        user = self.request.user
        if not (user.is_superuser or user.role == "ADMIN"):
            raise PermissionDenied("Only the school admin can change facility records.")

    def perform_create(self, serializer):
        self._require_admin()
        super().perform_create(serializer)

    def perform_update(self, serializer):
        self._require_admin()
        serializer.save()

    def perform_destroy(self, instance):
        self._require_admin()
        instance.delete()


class NavSectionViewSet(AdminWriteMixin, SchoolScopedViewSet):
    """Admin-created sidebar headings."""

    queryset = NavSection.objects.prefetch_related("categories__facilities").all()
    serializer_class = NavSectionSerializer

    def perform_destroy(self, instance):
        self._require_admin()
        # Categories fall back to the built-in Facilities heading.
        instance.categories.update(section=None)
        instance.delete()


class FacilityCategoryViewSet(AdminWriteMixin, SchoolScopedViewSet):
    """Department groupings — Transport, Dormitories, Libraries, Laboratories…"""

    queryset = FacilityCategory.objects.prefetch_related("facilities").all()
    serializer_class = FacilityCategorySerializer
    search_fields = ["name"]

    def perform_destroy(self, instance):
        self._require_admin()
        if instance.facilities.exists():
            raise ValidationError(
                "Move or remove the facilities in this category before deleting it."
            )
        instance.delete()


class FacilityViewSet(AdminWriteMixin, SchoolScopedViewSet):
    queryset = Facility.objects.select_related("category").prefetch_related(
        "assignments", "supplies"
    ).all()
    serializer_class = FacilitySerializer
    filterset_fields = ["category", "active"]
    search_fields = ["name", "location"]

    def get_serializer_class(self):
        # The detail view carries staff and supplies; the list stays light.
        if self.action == "retrieve":
            return FacilityDetailSerializer
        return FacilitySerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == "retrieve":
            return qs.prefetch_related(
                "assignments__teacher__user", "assignments__support_staff", "supplies"
            )
        return qs

    def perform_destroy(self, instance):
        self._require_admin()
        instance.delete()


class FacilityAssignmentViewSet(AdminWriteMixin, SchoolScopedViewSet):
    queryset = FacilityAssignment.objects.select_related(
        "teacher__user", "support_staff", "facility"
    ).all()
    serializer_class = FacilityAssignmentSerializer
    filterset_fields = ["facility", "teacher", "support_staff"]


class SupplyViewSet(AdminWriteMixin, SchoolScopedViewSet):
    queryset = Supply.objects.select_related("facility").all()
    serializer_class = SupplySerializer
    filterset_fields = ["facility"]
    search_fields = ["item"]


class FacilityBulkImportView(APIView):
    """GET/POST /api/facilities/bulk/ — the school's plant in one spreadsheet.

    Categories are created as they appear; a Staff Assigned column posts named
    staff (matched against the register) to each facility. Dry-run first, as
    everywhere: nothing is written until commit=true.
    """

    parser_classes = [MultiPartParser, FormParser]

    def _require_admin(self, user):
        if not (user.is_superuser or user.role == "ADMIN"):
            raise PermissionDenied("Only the school admin can import facilities.")

    def get(self, request):
        from django.http import HttpResponse

        from .bulk_import import template_csv

        self._require_admin(request.user)
        response = HttpResponse(template_csv(), content_type="text/csv")
        response["Content-Disposition"] = (
            'attachment; filename="facilities_import_template.csv"'
        )
        return response

    def post(self, request):
        self._require_admin(request.user)
        upload = request.FILES.get("file")
        if upload is None:
            return Response({"detail": "Attach a CSV file."}, status=400)

        from .bulk_import import commit, parse

        rows, errors, mapping = parse(upload, request.user.school)
        wants_commit = str(request.data.get("commit", "")).lower() in ("true", "1", "yes")
        body = {
            "recognised_columns": sorted(set(mapping.values())),
            "ready": len(rows),
            "problems": errors,
            "preview": [
                {
                    "row": r["_row"],
                    "name": r["name"],
                    "category": r["category"],
                    "capacity": r.get("capacity"),
                    "staff": ", ".join(name for name, _hit in r["_staff"]),
                }
                for r in rows[:50]
            ],
            "committed": False,
        }
        if not wants_commit:
            return Response(body)
        if not rows:
            return Response(
                {**body, "detail": "Nothing to import — every row has a problem."},
                status=400,
            )
        created = commit(rows, school=request.user.school)
        body["committed"] = True
        body["created"] = created
        return Response(body, status=201)
