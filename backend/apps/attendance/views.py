from django.db import transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.models import IdempotentRequest
from apps.common.views import IDEMPOTENCY_HEADER, IdempotencyMixin, SchoolScopedViewSet
from apps.students.models import Learner

from .models import AttendanceRecord
from .serializers import AttendanceRecordSerializer, BulkAttendanceSerializer


class AttendanceViewSet(IdempotencyMixin, SchoolScopedViewSet):
    queryset = AttendanceRecord.objects.select_related("learner").all()
    serializer_class = AttendanceRecordSerializer
    filterset_fields = ["learner", "date", "status"]


class AttendanceBulkView(APIView):
    """POST a whole class register at once. Offline-tolerant twice over:
    an Idempotency-Key header makes the request replay-safe, and each row is
    upserted on (learner, date) so partial retries converge instead of erroring."""

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

        serializer = BulkAttendanceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        date = serializer.validated_data["date"]
        records = serializer.validated_data["records"]

        school = request.user.school
        valid_ids = set(
            Learner.objects.filter(school=school, pk__in=[r.get("learner") for r in records])
            .values_list("pk", flat=True)
        )

        created, updated, skipped = 0, 0, []
        with transaction.atomic():
            for row in records:
                learner_id = row.get("learner")
                if learner_id not in valid_ids:
                    skipped.append(learner_id)
                    continue
                _, was_created = AttendanceRecord.objects.update_or_create(
                    learner_id=learner_id,
                    date=date,
                    defaults={"status": row.get("status", "P"), "school": school},
                )
                created += was_created
                updated += not was_created

        body = {"date": str(date), "created": created, "updated": updated, "skipped": skipped}
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
