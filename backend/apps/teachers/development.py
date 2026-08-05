"""Professional development records and peer review of schemes of work.

Both are the supportive half of brief §4. The analysis views say what happened
in a teacher's classes; these two say what the school is doing about it.

`ProfessionalDevelopmentRecord` has existed as a model since the first build but
was reachable only through Django admin. It is exposed here, with TPD points —
the unit TSC counts — totalled per teacher.
"""

from django.db.models import Sum
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.views import SchoolScopedViewSet

from .analysis import school_overview, teacher_analysis
from .models import (
    PeerReview,
    ProfessionalDevelopmentRecord,
    SchemeOfWork,
    Teacher,
)


class PdRecordSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source="teacher.__str__", read_only=True)

    class Meta:
        model = ProfessionalDevelopmentRecord
        fields = "__all__"
        read_only_fields = ["school"]
        extra_kwargs = {"teacher": {"required": False}}


class PdRecordViewSet(SchoolScopedViewSet):
    """A teacher logs their own training; the admin may log anyone's."""

    queryset = ProfessionalDevelopmentRecord.objects.select_related(
        "teacher__user"
    ).all()
    serializer_class = PdRecordSerializer
    filterset_fields = ["teacher", "provider"]
    search_fields = ["title", "provider"]

    def _own_teacher(self):
        return getattr(self.request.user, "teacher_profile", None)

    def _is_admin(self):
        user = self.request.user
        return user.is_superuser or user.role == "ADMIN"

    def get_queryset(self):
        qs = super().get_queryset()
        if self._is_admin():
            return qs
        teacher = self._own_teacher()
        if teacher is None:
            return qs.none()
        # Plus anyone they supervise, so a head of department can see their line.
        from .supervision import visible_staff_ids

        return qs.filter(teacher=teacher) | qs.filter(
            teacher__user_id__in=visible_staff_ids(self.request.user)
        )

    def perform_create(self, serializer):
        teacher = serializer.validated_data.get("teacher") or self._own_teacher()
        if teacher is None:
            raise ValidationError({"teacher": "Select the teacher this record is for."})
        if not self._is_admin() and teacher != self._own_teacher():
            raise PermissionDenied("You can only log your own development records.")
        serializer.save(school=self.request.user.school, teacher=teacher)

    def perform_update(self, serializer):
        record = self.get_object()
        if not self._is_admin() and record.teacher != self._own_teacher():
            raise PermissionDenied("You can only edit your own development records.")
        serializer.save()

    def perform_destroy(self, instance):
        if not self._is_admin() and instance.teacher != self._own_teacher():
            raise PermissionDenied("You can only remove your own development records.")
        instance.delete()

    @action(detail=False)
    def summary(self, request):
        """TPD points per teacher — the unit TSC counts."""
        rows = (
            self.get_queryset()
            .values("teacher", "teacher__user__first_name", "teacher__user__last_name")
            .annotate(points=Sum("tpd_points"))
            .order_by("-points")
        )
        return Response(
            [
                {
                    "teacher": row["teacher"],
                    "name": (
                        f"{row['teacher__user__first_name']} "
                        f"{row['teacher__user__last_name']}"
                    ).strip(),
                    "tpd_points": row["points"] or 0,
                }
                for row in rows
            ]
        )


class TeacherAnalysisView(APIView):
    """GET /api/teachers/<id>/analysis/ — one teacher's classes."""

    def get(self, request, teacher_id):
        teacher = Teacher.objects.filter(
            school=request.user.school, pk=teacher_id
        ).select_related("user").first()
        if teacher is None:
            return Response({"detail": "Teacher not found."}, status=404)

        user = request.user
        is_admin = user.is_superuser or user.role == "ADMIN"
        own = getattr(user, "teacher_profile", None)
        if not is_admin and teacher != own:
            # A supervisor may look at their own line, nobody else.
            from .supervision import visible_staff_ids

            if teacher.user_id not in visible_staff_ids(user):
                raise PermissionDenied(
                    "You can only see your own analysis, or that of staff you supervise."
                )

        year = request.query_params.get("year")
        term = request.query_params.get("term")
        return Response(
            teacher_analysis(
                teacher,
                year=int(year) if year else None,
                term=int(term) if term else None,
            )
        )


class SchoolAnalysisView(APIView):
    """GET /api/school/analysis/ — every teacher, for the head."""

    def get(self, request):
        user = request.user
        is_admin = user.is_superuser or user.role == "ADMIN"
        if not is_admin:
            from .supervision import SCOPE_WHOLE_SCHOOL, rank_level

            if rank_level(user) < SCOPE_WHOLE_SCHOOL:
                raise PermissionDenied(
                    "Only the head teacher, deputy or admin sees the whole school."
                )
        year = request.query_params.get("year")
        term = request.query_params.get("term")
        return Response(
            school_overview(
                user.school,
                year=int(year) if year else None,
                term=int(term) if term else None,
            )
        )


class PeerReviewSerializer(serializers.ModelSerializer):
    reviewer_name = serializers.CharField(
        source="reviewer.get_full_name", read_only=True
    )
    verdict_label = serializers.CharField(source="get_verdict_display", read_only=True)
    scheme_label = serializers.CharField(source="scheme.__str__", read_only=True)

    class Meta:
        model = PeerReview
        fields = "__all__"
        read_only_fields = ["school", "reviewer"]


class PeerReviewViewSet(SchoolScopedViewSet):
    """Colleagues commenting on each other's schemes of work."""

    serializer_class = PeerReviewSerializer
    filterset_fields = ["scheme", "verdict"]

    def get_queryset(self):
        return PeerReview.objects.select_related(
            "reviewer", "scheme__learning_area", "scheme__teacher__user"
        ).all()

    def perform_create(self, serializer):
        user = self.request.user
        teacher = getattr(user, "teacher_profile", None)
        if teacher is None:
            raise PermissionDenied("Only teaching staff can peer-review a scheme.")
        scheme = serializer.validated_data["scheme"]
        if scheme.school_id != user.school_id:
            raise PermissionDenied("That scheme belongs to another school.")
        if scheme.teacher_id == teacher.id:
            raise ValidationError(
                {"scheme": "A peer review is a colleague's view — you cannot review your own."}
            )
        # The reviewer is set here rather than sent, so DRF cannot derive the
        # uniqueness check itself — without this a second submission would hit
        # the database constraint and surface as a 500.
        if PeerReview.objects.filter(scheme=scheme, reviewer=user).exists():
            raise ValidationError(
                {"scheme": "You have already reviewed this scheme — edit that review instead."}
            )
        serializer.save(school=user.school, reviewer=user)

    def perform_update(self, serializer):
        review = self.get_object()
        if review.reviewer_id != self.request.user.id:
            raise PermissionDenied("You can only edit your own review.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.reviewer_id != self.request.user.id:
            raise PermissionDenied("You can only withdraw your own review.")
        instance.delete()


class PeerReviewQueueView(APIView):
    """GET /api/peer-review/queue/ — colleagues' schemes I could comment on.

    Same subject, so the reviewer knows the material; not my own; not already
    reviewed by me.
    """

    def get(self, request):
        teacher = getattr(request.user, "teacher_profile", None)
        if teacher is None:
            raise PermissionDenied("Only teaching staff can peer-review a scheme.")

        from apps.timetable.models import LessonRequirement

        my_areas = set(
            teacher.learning_areas.values_list("id", flat=True)
        ) | set(
            LessonRequirement.objects.filter(teacher=teacher).values_list(
                "learning_area_id", flat=True
            )
        )
        reviewed = set(
            PeerReview.objects.filter(reviewer=request.user).values_list(
                "scheme_id", flat=True
            )
        )
        schemes = (
            SchemeOfWork.objects.filter(
                school=request.user.school, learning_area_id__in=my_areas
            )
            .exclude(teacher=teacher)
            .exclude(id__in=reviewed)
            .select_related("teacher__user", "learning_area")
        )
        return Response(
            {
                "subjects": sorted(my_areas),
                "schemes": [
                    {
                        "id": s.id,
                        "label": str(s),
                        "teacher": s.teacher.user.get_full_name()
                        or s.teacher.user.username,
                        "learning_area": s.learning_area.name,
                        "grade": s.grade,
                        "term": s.term,
                        "year": s.year,
                        "status": s.status,
                        "peer_reviews": s.peer_reviews.count(),
                    }
                    for s in schemes
                ],
            }
        )
