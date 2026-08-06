"""Promotion API. Admin-only throughout — this is the one operation that can
rearrange every register in the school."""

from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.views import SchoolScopedViewSet
from apps.schools.moe import PATHWAYS, TRANSITIONS

from .models import AcademicYear, PromotionOutcome, PromotionRun
from .services import apply_run, build_run, revert_run, summarise


def require_admin(user):
    if not (user.is_superuser or user.role == "ADMIN"):
        raise PermissionDenied("Only the school admin can run promotions.")


class AcademicYearSerializer(serializers.ModelSerializer):
    class Meta:
        model = AcademicYear
        fields = "__all__"
        read_only_fields = ["school"]


class AcademicYearViewSet(SchoolScopedViewSet):
    queryset = AcademicYear.objects.all()
    serializer_class = AcademicYearSerializer
    filterset_fields = ["is_current"]

    def perform_create(self, serializer):
        require_admin(self.request.user)
        if serializer.validated_data.get("is_current"):
            AcademicYear.objects.filter(
                school=self.request.user.school, is_current=True
            ).update(is_current=False)
        super().perform_create(serializer)

    def perform_update(self, serializer):
        require_admin(self.request.user)
        if serializer.validated_data.get("is_current"):
            AcademicYear.objects.filter(
                school=self.request.user.school, is_current=True
            ).exclude(pk=serializer.instance.pk).update(is_current=False)
        serializer.save()

    def perform_destroy(self, instance):
        require_admin(self.request.user)
        instance.delete()


class OutcomeSerializer(serializers.ModelSerializer):
    learner_name = serializers.CharField(source="learner.full_name", read_only=True)
    admission_number = serializers.CharField(
        source="learner.admission_number", read_only=True
    )
    from_grade = serializers.IntegerField(source="learner.grade", read_only=True)
    action_label = serializers.CharField(source="get_action_display", read_only=True)
    pathway_label = serializers.CharField(
        source="pathway.get_code_display", read_only=True, default=None
    )

    class Meta:
        model = PromotionOutcome
        fields = [
            "id", "run", "learner", "learner_name", "admission_number",
            "from_grade", "action", "action_label", "to_grade", "to_stream",
            "pathway", "pathway_label", "pathway_track", "pathway_rationale",
            "note", "applied",
        ]
        read_only_fields = ["run", "learner", "applied"]


class RunSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    created_by_name = serializers.CharField(
        source="created_by.get_full_name", read_only=True, default=None
    )
    summary = serializers.SerializerMethodField()

    class Meta:
        model = PromotionRun
        fields = "__all__"
        read_only_fields = [
            "school", "status", "created_by", "applied_at", "applied_by",
            "reversed_at", "reversed_by",
        ]

    def get_summary(self, obj):
        return summarise(obj)


class PromotionRunViewSet(SchoolScopedViewSet):
    queryset = PromotionRun.objects.select_related(
        "created_by", "applied_by", "reversed_by"
    ).all()
    serializer_class = RunSerializer
    filterset_fields = ["status", "from_year", "to_year"]

    def create(self, request, *args, **kwargs):
        """Preview: build the run without changing anything."""
        require_admin(request.user)
        from_year = request.data.get("from_year")
        to_year = request.data.get("to_year")
        grade = request.data.get("grade", None)
        try:
            from_year = int(from_year)
            to_year = int(to_year)
            grade = int(grade) if grade not in (None, "") else None
        except (TypeError, ValueError):
            raise ValidationError({"detail": "from_year and to_year must be numbers."})
        if to_year <= from_year:
            raise ValidationError(
                {"to_year": "The new year must come after the one being closed."}
            )
        if PromotionRun.objects.filter(
            school=request.user.school, status=PromotionRun.Status.DRAFT
        ).exists():
            raise ValidationError(
                {"detail": "A draft promotion already exists. Apply or delete it first."}
            )

        run = build_run(
            school=request.user.school,
            from_year=from_year,
            to_year=to_year,
            grade=grade,
            user=request.user,
            note=request.data.get("note", ""),
        )
        return Response(
            RunSerializer(run, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    def perform_destroy(self, instance):
        require_admin(self.request.user)
        if instance.status != PromotionRun.Status.DRAFT:
            raise PermissionDenied(
                "An applied run is the record of what happened — reverse it instead."
            )
        instance.delete()

    @action(detail=True)
    def outcomes(self, request, pk=None):
        run = self.get_object()
        rows = run.outcomes.select_related("learner", "pathway")
        return Response(OutcomeSerializer(rows, many=True).data)

    @action(detail=True, methods=["post"])
    def apply(self, request, pk=None):
        require_admin(request.user)
        run = self.get_object()

        # A Grade 10 place without a pathway is an incomplete record, not a
        # detail to fix later.
        missing = run.outcomes.filter(
            action=PromotionOutcome.Action.PROMOTE, to_grade=10, pathway__isnull=True
        ).count()
        if missing:
            return Response(
                {
                    "detail": (
                        f"{missing} learner(s) moving into Grade 10 have no pathway. "
                        "Confirm a pathway for each before applying."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            apply_run(run, user=request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(RunSerializer(run, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def revert(self, request, pk=None):
        require_admin(request.user)
        run = self.get_object()
        try:
            revert_run(run, user=request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(RunSerializer(run, context={"request": request}).data)


class PromotionOutcomeViewSet(SchoolScopedViewSet):
    """Adjusting one learner inside a draft run."""

    queryset = PromotionOutcome.objects.select_related("learner", "run", "pathway").all()
    serializer_class = OutcomeSerializer
    filterset_fields = ["run", "action"]

    def perform_update(self, serializer):
        require_admin(self.request.user)
        outcome = self.get_object()
        if not outcome.run.is_editable:
            raise PermissionDenied(
                "This run has already been applied. Reverse it to make changes."
            )
        serializer.save()

    def perform_create(self, serializer):
        raise PermissionDenied("Outcomes are created by previewing a run.")

    def perform_destroy(self, instance):
        raise PermissionDenied("Remove a learner by marking them as transferred out.")


class TransitionInfoView(APIView):
    """GET /api/promotions/transitions/ — the MoE transitions and pathways the
    UI needs, straight from the canon."""

    def get(self, request):
        current = AcademicYear.objects.filter(
            school=request.user.school, is_current=True
        ).first()
        return Response(
            {
                "transitions": TRANSITIONS,
                "pathways": PATHWAYS,
                "current_year": current.year if current else None,
                "draft_run": PromotionRun.objects.filter(
                    school=request.user.school, status=PromotionRun.Status.DRAFT
                ).values_list("id", flat=True).first(),
            }
        )
