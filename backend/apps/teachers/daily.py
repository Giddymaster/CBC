"""Staff roll-call and lesson plans.

Both had a model and an API-less existence: `TeacherAttendance` was written only
by the seed script, and `LessonPlan` had a viewset but nothing that let a
teacher fill one in against the scheme it belongs to.
"""

from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import LessonPlan, SchemeOfWork, Teacher, TeacherAttendance


class StaffRollCallView(APIView):
    """GET/POST /api/staff/roll-call/?date= — who is in today.

    Mirrors the learner register: one request for the whole staff list, and
    re-submitting corrects rather than duplicating.
    """

    def _require_office(self, user):
        if user.is_superuser or user.role == "ADMIN":
            return
        from .supervision import SCOPE_WHOLE_SCHOOL, rank_level

        if rank_level(user) < SCOPE_WHOLE_SCHOOL:
            raise PermissionDenied(
                "Staff attendance is taken by the head teacher, deputy or admin."
            )

    def _date(self, request):
        raw = request.query_params.get("date") or request.data.get("date")
        if not raw:
            return timezone.localdate(), None
        try:
            return timezone.datetime.strptime(raw, "%Y-%m-%d").date(), None
        except ValueError:
            return None, "date must be YYYY-MM-DD"

    def get(self, request):
        self._require_office(request.user)
        day, error = self._date(request)
        if error:
            return Response({"detail": error}, status=400)

        school = request.user.school
        marked = {
            record.teacher_id: record.status
            for record in TeacherAttendance.objects.filter(school=school, date=day)
        }
        teachers = Teacher.objects.filter(
            school=school, user__is_active=True
        ).select_related("user")
        rows = [
            {
                "teacher": t.id,
                "name": t.user.get_full_name() or t.user.username,
                "rank": t.get_rank_display(),
                "tsc_number": t.tsc_number,
                "status": marked.get(t.id),
            }
            for t in teachers
        ]
        return Response(
            {
                "date": day.isoformat(),
                "staff": rows,
                "totals": {
                    "present": sum(1 for r in rows if r["status"] == "P"),
                    "absent": sum(1 for r in rows if r["status"] == "A"),
                    "on_leave": sum(1 for r in rows if r["status"] == "L"),
                    "not_marked": sum(1 for r in rows if r["status"] is None),
                },
            }
        )

    def post(self, request):
        self._require_office(request.user)
        day, error = self._date(request)
        if error:
            return Response({"detail": error}, status=400)

        school = request.user.school
        valid = set(
            Teacher.objects.filter(school=school).values_list("id", flat=True)
        )
        saved, skipped = [], []
        for row in request.data.get("records", []):
            teacher_id = row.get("teacher")
            status_code = row.get("status")
            if teacher_id not in valid or status_code not in ("P", "A", "L"):
                skipped.append(teacher_id)
                continue
            TeacherAttendance.objects.update_or_create(
                teacher_id=teacher_id,
                date=day,
                defaults={"status": status_code, "school": school},
            )
            saved.append(teacher_id)
        return Response({"date": day.isoformat(), "saved": saved, "skipped": skipped})


class LessonPlanSerializer(serializers.ModelSerializer):
    scheme_label = serializers.CharField(source="scheme.__str__", read_only=True)

    class Meta:
        model = LessonPlan
        fields = "__all__"
        read_only_fields = ["school"]


class SchemeLessonPlansView(APIView):
    """GET/POST /api/schemes-of-work/<id>/lesson-plans/

    A lesson plan belongs to a week of a scheme, so it is reached through the
    scheme rather than floating free.
    """

    def _scheme(self, request, scheme_id, *, for_write):
        scheme = SchemeOfWork.objects.filter(
            school=request.user.school, pk=scheme_id
        ).select_related("teacher").first()
        if scheme is None:
            raise PermissionDenied("Scheme not found at this school.")

        user = request.user
        is_admin = user.is_superuser or user.role == "ADMIN"
        own = getattr(user, "teacher_profile", None)
        if for_write and not is_admin and scheme.teacher_id != getattr(own, "id", None):
            raise PermissionDenied("You can only plan lessons for your own scheme.")
        return scheme

    def get(self, request, scheme_id):
        scheme = self._scheme(request, scheme_id, for_write=False)
        plans = LessonPlan.objects.filter(scheme=scheme)
        return Response(
            {
                "scheme": str(scheme),
                "weeks": scheme.content.get("weeks", []) if scheme.content else [],
                "lesson_plans": LessonPlanSerializer(plans, many=True).data,
            }
        )

    def post(self, request, scheme_id):
        scheme = self._scheme(request, scheme_id, for_write=True)
        serializer = LessonPlanSerializer(data={**request.data, "scheme": scheme.id})
        serializer.is_valid(raise_exception=True)
        # One plan per lesson: re-posting the same week and number edits it.
        plan, _created = LessonPlan.objects.update_or_create(
            scheme=scheme,
            week=serializer.validated_data["week"],
            lesson_number=serializer.validated_data["lesson_number"],
            defaults={
                "school": scheme.school,
                "strand": serializer.validated_data.get("strand", ""),
                "sub_strand": serializer.validated_data.get("sub_strand", ""),
                "learning_outcomes": serializer.validated_data.get("learning_outcomes", ""),
                "resources": serializer.validated_data.get("resources", ""),
            },
        )
        return Response(
            LessonPlanSerializer(plan).data, status=status.HTTP_201_CREATED
        )
