from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import serializers as drf_serializers
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.audit import record as audit
from apps.common.models import IdempotentRequest
from apps.common.views import (
    IDEMPOTENCY_HEADER,
    AdminWriteMixin,
    IdempotencyMixin,
    SchoolScopedViewSet,
)
from apps.students.models import Learner

from .models import Assessment, LearningArea, Score
from .pdf import render_report_card_pdf
from .reports import build_report_card
from .serializers import AssessmentSerializer, LearningAreaSerializer, ScoreSerializer
from .tasks import generate_class_report_cards


class LearningAreaViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    """Learning areas are national — shared by every school on the platform.

    A school admin may add or correct one, but deletion is reserved for a
    platform superuser: the FK from Assessment cascades, so deleting a
    learning area would take every school's assessments and scores in that
    subject with it."""

    queryset = LearningArea.objects.all()
    serializer_class = LearningAreaSerializer
    search_fields = ["name", "code"]

    def perform_destroy(self, instance):
        if not self.request.user.is_superuser:
            raise PermissionDenied(
                "Deleting a learning area cascades into every school's scores — "
                "platform administrators only."
            )
        instance.delete()

    @action(detail=False, methods=["post"], url_path="seed-moe")
    def seed_moe(self, request):
        """Load the KICD/MoE canon of learning areas with their level grades.

        Idempotent: an area that already exists (by name or code) keeps its
        row — its grades become the union of what it had and what the canon
        says — so a school that already typed some areas loses nothing.
        """
        self._require_admin_write()
        from apps.schools.moe import LEARNING_AREAS

        created = updated = 0
        for entry in LEARNING_AREAS:
            area = (
                LearningArea.objects.filter(name__iexact=entry["name"]).first()
                or LearningArea.objects.filter(code__iexact=entry["code"]).first()
            )
            if area is None:
                LearningArea.objects.create(
                    name=entry["name"], code=entry["code"], grades=entry["grades"]
                )
                created += 1
            else:
                merged = sorted(set(area.grades or []) | set(entry["grades"]))
                if merged != sorted(area.grades or []):
                    area.grades = merged
                    area.save(update_fields=["grades"])
                    updated += 1
        return Response({"created": created, "updated": updated})


class AssessmentViewSet(SchoolScopedViewSet):
    """Assessments are created by staff — a teacher adds a CAT or exam for
    the classes they mark; parents only ever read results."""

    queryset = Assessment.objects.select_related("learning_area").all()
    serializer_class = AssessmentSerializer
    filterset_fields = ["kind", "learning_area", "grade", "stream", "term", "year"]

    def _require_staff(self):
        user = self.request.user
        if not (user.is_superuser or user.role in ("ADMIN", "TEACHER")):
            raise PermissionDenied("Assessments are managed by staff.")

    def perform_create(self, serializer):
        self._require_staff()
        super().perform_create(serializer)

    def perform_update(self, serializer):
        self._require_staff()
        serializer.save()

    def perform_destroy(self, instance):
        # Deleting an assessment cascades into its scores — office only.
        user = self.request.user
        if not (user.is_superuser or user.role == "ADMIN"):
            raise PermissionDenied(
                "Deleting an assessment removes its recorded marks — ask the office."
            )
        instance.delete()


class ScoreViewSet(IdempotencyMixin, SchoolScopedViewSet):
    """Score entry is offline-tolerant: send an Idempotency-Key header and
    retries from flaky connections will not double-write."""

    queryset = Score.objects.select_related("assessment", "learner").all()
    serializer_class = ScoreSerializer
    filterset_fields = ["assessment", "learner", "competency_level"]


class BulkScoreSerializer(drf_serializers.Serializer):
    """One class's marks for one assessment in a single retryable request."""

    assessment = drf_serializers.IntegerField()
    records = drf_serializers.ListField(
        child=drf_serializers.DictField(), help_text='[{"learner": id, "marks": 87.5}, ...]'
    )


class ScoreBulkView(APIView):
    """POST a whole class's marks at once. Offline-tolerant like bulk
    attendance: Idempotency-Key replay-safe, rows upserted on
    (assessment, learner) so partial retries converge. Returns the derived
    competency level per learner."""

    def post(self, request):
        key = request.headers.get(IDEMPOTENCY_HEADER)
        if key:
            existing = IdempotentRequest.objects.filter(key=key).first()
            if existing:
                return Response(
                    existing.response_body,
                    status=existing.status_code,
                    headers={"X-Idempotent-Replay": "true"},
                )

        serializer = BulkScoreSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        school = request.user.school
        assessment = get_object_or_404(
            Assessment.objects.filter(school=school), pk=data["assessment"]
        )
        valid_ids = set(
            Learner.objects.filter(
                school=school, pk__in=[r.get("learner") for r in data["records"]]
            ).values_list("pk", flat=True)
        )

        saved, skipped = [], []
        with transaction.atomic():
            for row in data["records"]:
                learner_id = row.get("learner")
                marks = row.get("marks")
                if learner_id not in valid_ids or marks in (None, ""):
                    skipped.append(learner_id)
                    continue
                marks = float(marks)
                if marks < 0 or marks > assessment.max_marks:
                    skipped.append(learner_id)
                    continue
                previous = Score.objects.filter(
                    assessment=assessment, learner_id=learner_id
                ).values_list("marks", "competency_level").first()
                score, _ = Score.objects.update_or_create(
                    assessment=assessment,
                    learner_id=learner_id,
                    defaults={"marks": marks, "school": school},
                )
                # Only a *change* is worth recording. Entering a mark for the
                # first time is the normal path and would bury the corrections.
                if previous and float(previous[0]) != marks:
                    audit(
                        actor=request.user,
                        school=school,
                        action="SCORE_CHANGED",
                        target=score,
                        label=f"{score.learner} — {assessment}",
                        detail={
                            "from": float(previous[0]),
                            "to": marks,
                            "from_level": previous[1],
                            "to_level": score.competency_level,
                        },
                    )
                saved.append(
                    {
                        "learner": learner_id,
                        "marks": float(score.marks),
                        "competency_level": score.competency_level,
                    }
                )

        body = {"assessment": assessment.id, "saved": saved, "skipped": skipped}
        response = Response(body, status=status.HTTP_200_OK)
        if key:
            IdempotentRequest.objects.create(
                key=key,
                method=request.method,
                path=request.path,
                status_code=response.status_code,
                response_body=body,
            )
        return response


class ReportCardView(APIView):
    """Term report card: per learning area, marks + competency level per
    assessment kind, ready for PDF rendering or the parent portal."""

    def get(self, request, learner_id):
        learner = get_object_or_404(
            Learner.objects.filter(school=request.user.school).select_related("pathway", "school"),
            pk=learner_id,
        )
        term = request.query_params.get("term")
        year = request.query_params.get("year")
        return Response(build_report_card(learner, term=term, year=year))


class ReportCardPdfView(APIView):
    """Download one learner's report card as PDF (rendered on the fly)."""

    def get(self, request, learner_id):
        learner = get_object_or_404(
            Learner.objects.filter(school=request.user.school).select_related("pathway", "school"),
            pk=learner_id,
        )
        term = request.query_params.get("term")
        year = request.query_params.get("year")
        pdf_bytes = render_report_card_pdf(build_report_card(learner, term=term, year=year))
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'inline; filename="report_{learner.admission_number}.pdf"'
        )
        return response


class GenerateClassReportCardsSerializer(drf_serializers.Serializer):
    grade = drf_serializers.IntegerField()
    stream = drf_serializers.CharField(allow_blank=True, default="")
    term = drf_serializers.IntegerField(min_value=1, max_value=3)
    year = drf_serializers.IntegerField()


class GenerateClassReportCardsView(APIView):
    """Queue PDF generation for a whole class (Celery; inline in dev)."""

    def post(self, request):
        user = request.user
        if not (user.is_superuser or user.role in ("ADMIN", "TEACHER")):
            raise PermissionDenied("Generating class report cards is a staff job.")
        serializer = GenerateClassReportCardsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = generate_class_report_cards.delay(
            request.user.school_id, data["grade"], data["stream"], data["term"], data["year"]
        )
        body = {"queued": True, "task_id": result.id}
        if result.ready():  # eager mode (dev): files are already on disk
            body["generated"] = result.get()
        return Response(body, status=status.HTTP_202_ACCEPTED)
