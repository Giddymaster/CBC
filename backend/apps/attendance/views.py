import calendar
from datetime import date as date_cls

from django.db import transaction
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.models import IdempotentRequest
from apps.common.views import IDEMPOTENCY_HEADER, IdempotencyMixin, SchoolScopedViewSet
from apps.students.models import Learner

from .models import AttendanceRecord
from .serializers import AttendanceRecordSerializer, BulkAttendanceSerializer


class AttendanceViewSet(IdempotencyMixin, SchoolScopedViewSet):
    """The daily register. The bulk endpoint below enforces class-teacher-only
    marking; this per-row viewset must not become the way around it, so writes
    are staff-only and a learner must belong to the caller's school. Reading is
    staff-only too — a parent has no business over the whole school's register.
    """

    queryset = AttendanceRecord.objects.select_related("learner").all()
    serializer_class = AttendanceRecordSerializer
    filterset_fields = ["learner", "date", "status"]

    def _require_staff(self):
        user = self.request.user
        if not (user.is_superuser or user.role in ("ADMIN", "TEACHER", "SUPPORT")):
            raise PermissionDenied("The attendance register is staff-only.")

    def get_queryset(self):
        self._require_staff()
        return super().get_queryset()

    def _check_learner(self, serializer):
        learner = serializer.validated_data.get("learner")
        if learner is not None and learner.school_id != self.request.user.school_id:
            raise PermissionDenied("That learner is not at your school.")

    def perform_create(self, serializer):
        self._require_staff()
        self._check_learner(serializer)
        super().perform_create(serializer)

    def perform_update(self, serializer):
        self._require_staff()
        self._check_learner(serializer)
        serializer.save()

    def perform_destroy(self, instance):
        self._require_staff()
        instance.delete()


class AttendanceMonthView(APIView):
    """GET /api/attendance/month/?year=&month=&grade=&stream= — one month of a
    class's register: every learner (no page cap) × every day, for the
    wall-calendar view. Staff read it; marking stays with the class teacher."""

    def get(self, request):
        user = request.user
        if not (user.is_superuser or user.role in ("ADMIN", "TEACHER")):
            raise PermissionDenied("The attendance register is staff-only.")

        try:
            year = int(request.query_params.get("year", 0))
            month = int(request.query_params.get("month", 0))
        except ValueError:
            year = month = 0
        if not (year and 1 <= month <= 12):
            from django.utils import timezone

            today = timezone.localdate()
            year, month = today.year, today.month

        learners = Learner.objects.filter(school=user.school, active=True)
        grade = request.query_params.get("grade")
        if grade not in (None, ""):
            learners = learners.filter(grade=int(grade))
        stream = request.query_params.get("stream")
        if stream not in (None, ""):
            learners = learners.filter(stream=stream)
        learners = list(learners.order_by("grade", "stream", "admission_number"))

        first = date_cls(year, month, 1)
        last = date_cls(year, month, calendar.monthrange(year, month)[1])
        marks = {}
        for record in AttendanceRecord.objects.filter(
            school=user.school,
            learner_id__in=[l.id for l in learners],
            date__range=(first, last),
        ):
            marks.setdefault(record.learner_id, {})[record.date.isoformat()] = (
                record.status
            )

        days = [
            {
                "date": date_cls(year, month, d).isoformat(),
                "dow": date_cls(year, month, d).weekday(),  # 0=Mon
                "week": date_cls(year, month, d).isocalendar()[1],
            }
            for d in range(1, last.day + 1)
            if date_cls(year, month, d).weekday() < 5  # school days only
        ]
        return Response({
            "year": year,
            "month": month,
            "days": days,
            "learners": [
                {
                    "id": l.id,
                    "name": l.full_name,
                    "admission_number": l.admission_number,
                    "grade": l.grade,
                    "stream": l.stream,
                    "marks": marks.get(l.id, {}),
                }
                for l in learners
            ],
        })


class AttendanceBulkView(APIView):
    """POST a whole class register at once. Offline-tolerant twice over:
    an Idempotency-Key header makes the request replay-safe, and each row is
    upserted on (learner, date) so partial retries converge instead of erroring.

    Marking is the CLASS teacher's job — not any teacher's, and not the
    office's. Each learner's mark is accepted only from the teacher seated as
    that class's class teacher; everyone else reads the register."""

    def post(self, request):
        from apps.students.models import ClassGroup

        teacher = getattr(request.user, "teacher_profile", None)
        if teacher is None:
            raise PermissionDenied(
                "The register is marked by the class teacher. Admin accounts "
                "can view attendance but not mark it."
            )
        my_classes = set(
            ClassGroup.objects.filter(class_teacher=teacher).values_list(
                "grade", "stream"
            )
        )
        if not my_classes:
            raise PermissionDenied(
                "Only a class teacher marks the register — you are not seated "
                "as any class's teacher. The head teacher assigns class "
                "teachers under School (Grades)."
            )
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
        learner_class = {
            pk: (grade, stream)
            for pk, grade, stream in Learner.objects.filter(
                school=school, pk__in=[r.get("learner") for r in records]
            ).values_list("pk", "grade", "stream")
        }

        valid_statuses = set(AttendanceRecord.Status.values)
        created, updated, skipped = 0, 0, []
        with transaction.atomic():
            for row in records:
                learner_id = row.get("learner")
                if (
                    learner_id not in learner_class
                    or learner_class[learner_id] not in my_classes
                    or row.get("status", "P") not in valid_statuses
                ):
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
