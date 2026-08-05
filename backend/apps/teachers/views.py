from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers as drf_serializers
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.common.views import SchoolScopedViewSet

from .models import LessonPlan, SchemeOfWork, Teacher
from .serializers import LessonPlanSerializer, SchemeOfWorkSerializer, TeacherSerializer
from .services.ai_scheme import generate_scheme


class TeacherViewSet(SchoolScopedViewSet):
    """Read-only for staff; only the admin may change a teacher record.

    Rank and supervisor live here, and rank decides how much of the school a
    login can see — so letting a teacher PATCH their own row would be a
    promotion anyone could grant themselves.
    """

    queryset = Teacher.objects.select_related("user").all()
    serializer_class = TeacherSerializer
    search_fields = ["tsc_number", "user__first_name", "user__last_name"]

    def _require_admin(self):
        user = self.request.user
        if not (user.is_superuser or user.role == "ADMIN"):
            raise PermissionDenied("Only the school admin can change staff records.")

    def perform_create(self, serializer):
        self._require_admin()
        super().perform_create(serializer)

    def perform_update(self, serializer):
        self._require_admin()
        serializer.save()

    def perform_destroy(self, instance):
        self._require_admin()
        instance.user.is_active = False
        instance.user.save(update_fields=["is_active"])


class GenerateSchemeSerializer(drf_serializers.Serializer):
    learning_area = drf_serializers.IntegerField()
    grade = drf_serializers.IntegerField()
    term = drf_serializers.IntegerField(min_value=1, max_value=3)
    year = drf_serializers.IntegerField()
    weeks = drf_serializers.IntegerField(min_value=1, max_value=14, default=10)
    lessons_per_week = drf_serializers.IntegerField(min_value=1, max_value=8, default=4)
    extra_instructions = drf_serializers.CharField(
        allow_blank=True, default="", max_length=2000
    )


class ReviewSchemeSerializer(drf_serializers.Serializer):
    decision = drf_serializers.ChoiceField(choices=["approve", "reject"])
    comment = drf_serializers.CharField(allow_blank=True, default="", max_length=2000)


class SchemeOfWorkViewSet(SchoolScopedViewSet):
    """Schemes of work with an upload + AI-generate + head-review workflow.

    - Multipart POST with a `document` file => source UPLOADED, status PENDING.
    - POST /generate/ => AI-drafted content, source GENERATED, status PENDING.
    - POST /<id>/review/ (admin only) => approve/reject with a comment.
    Teacher users are always attached as themselves.
    """

    queryset = SchemeOfWork.objects.select_related(
        "teacher__user", "learning_area", "reviewed_by"
    ).all()
    serializer_class = SchemeOfWorkSerializer
    filterset_fields = ["teacher", "grade", "term", "year", "learning_area", "status", "source"]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        """A teacher's own schemes only. Heads and admins see the whole queue —
        they are the ones who review them."""
        qs = super().get_queryset()
        user = self.request.user
        if user.is_superuser or user.role == "ADMIN":
            return qs
        teacher = self._own_teacher()
        if teacher is None:
            return qs.none()
        from .supervision import visible_staff_ids

        # Plus anything filed by staff who report to them, so a head of
        # department can follow their own line's planning.
        team = visible_staff_ids(user)
        return qs.filter(Q(teacher=teacher) | Q(teacher__user_id__in=team))

    def _own_teacher(self):
        return getattr(self.request.user, "teacher_profile", None)

    @staticmethod
    def _taught_area_ids(teacher):
        """Learning areas a teacher actually teaches: their assigned areas
        plus anything on their timetable requirements."""
        from apps.timetable.models import LessonRequirement

        ids = set(teacher.learning_areas.values_list("id", flat=True))
        ids |= set(
            LessonRequirement.objects.filter(teacher=teacher).values_list(
                "learning_area_id", flat=True
            )
        )
        return ids

    def _check_teaches(self, teacher, learning_area):
        if learning_area.id not in self._taught_area_ids(teacher):
            raise ValidationError(
                {
                    "learning_area": (
                        f"{teacher} does not teach {learning_area.name} — a scheme of "
                        "work can only be filed for a subject the teacher teaches."
                    )
                }
            )

    def perform_create(self, serializer):
        user = self.request.user
        extra = {}
        teacher = self._own_teacher()
        if teacher is not None:
            extra["teacher"] = teacher  # teachers always file under themselves
        elif not serializer.validated_data.get("teacher"):
            raise ValidationError({"teacher": "Select the teacher this scheme belongs to."})

        owner = extra.get("teacher") or serializer.validated_data.get("teacher")
        learning_area = serializer.validated_data.get("learning_area")
        if owner and learning_area:
            self._check_teaches(owner, learning_area)
        if serializer.validated_data.get("document"):
            extra["source"] = SchemeOfWork.Source.UPLOADED
            extra["status"] = SchemeOfWork.Status.PENDING
        if user.school_id is not None:
            extra["school"] = user.school
        serializer.save(**extra)

    @action(detail=False, methods=["post"])
    def generate(self, request):
        """AI-draft a scheme of work; lands in PENDING for the head to review."""
        teacher = self._own_teacher()
        if teacher is None:
            raise PermissionDenied("Only teacher accounts can generate schemes of work.")

        params = GenerateSchemeSerializer(data=request.data)
        params.is_valid(raise_exception=True)
        data = params.validated_data

        from apps.assessments.models import LearningArea

        try:
            learning_area = LearningArea.objects.get(pk=data["learning_area"])
        except LearningArea.DoesNotExist:
            raise ValidationError({"learning_area": "Unknown learning area."})
        self._check_teaches(teacher, learning_area)

        try:
            content = generate_scheme(
                learning_area=learning_area.name,
                learning_area_id=learning_area.id,
                school=teacher.school,
                grade=data["grade"],
                term=data["term"],
                year=data["year"],
                weeks=data["weeks"],
                lessons_per_week=data["lessons_per_week"],
                extra_instructions=data["extra_instructions"],
            )
        except Exception as exc:  # network/model failure => clean 502, nothing saved
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        scheme, _created = SchemeOfWork.objects.update_or_create(
            school=teacher.school,
            teacher=teacher,
            learning_area=learning_area,
            grade=data["grade"],
            term=data["term"],
            year=data["year"],
            defaults={
                "content": content,
                "source": SchemeOfWork.Source.GENERATED,
                "status": SchemeOfWork.Status.PENDING,
                "reviewed_by": None,
                "reviewed_at": None,
                "review_comment": "",
            },
        )
        return Response(
            SchemeOfWorkSerializer(scheme, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        """Admin/head approves or rejects a scheme."""
        user = request.user
        if not (user.is_superuser or user.role == "ADMIN"):
            raise PermissionDenied("Only the school admin/head can review schemes.")

        scheme = self.get_object()
        params = ReviewSchemeSerializer(data=request.data)
        params.is_valid(raise_exception=True)

        scheme.status = (
            SchemeOfWork.Status.APPROVED
            if params.validated_data["decision"] == "approve"
            else SchemeOfWork.Status.REJECTED
        )
        scheme.reviewed_by = user
        scheme.reviewed_at = timezone.now()
        scheme.review_comment = params.validated_data["comment"]
        scheme.save()

        from apps.common.audit import record as audit

        audit(
            actor=user,
            school=scheme.school,
            action="SCHEME_REVIEWED",
            target=scheme,
            label=str(scheme),
            detail={
                "decision": params.validated_data["decision"],
                "teacher": str(scheme.teacher),
                "comment": scheme.review_comment,
            },
        )
        return Response(SchemeOfWorkSerializer(scheme, context={"request": request}).data)

    @action(detail=False, methods=["post"], url_path="submit/(?P<scheme_pk>[^/.]+)")
    def submit(self, request, scheme_pk=None):
        """Teacher submits a DRAFT/REJECTED scheme (back) into review."""
        scheme = self.get_object_or_404_scoped(scheme_pk)
        teacher = self._own_teacher()
        is_admin = request.user.is_superuser or request.user.role == "ADMIN"
        if not is_admin and (teacher is None or scheme.teacher_id != teacher.id):
            raise PermissionDenied("You can only submit your own scheme of work.")
        scheme.status = SchemeOfWork.Status.PENDING
        scheme.save(update_fields=["status", "updated_at"])
        return Response(SchemeOfWorkSerializer(scheme, context={"request": request}).data)

    def get_object_or_404_scoped(self, pk):
        from django.shortcuts import get_object_or_404

        return get_object_or_404(self.get_queryset(), pk=pk)


class LessonPlanViewSet(SchoolScopedViewSet):
    queryset = LessonPlan.objects.all()
    serializer_class = LessonPlanSerializer
    filterset_fields = ["scheme", "week"]
