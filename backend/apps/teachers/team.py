"""Supervisor-side views: the team they oversee, and per-person drill-down
with that person's reports, assigned work and a message thread."""

from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.views import SchoolScopedViewSet

from .models import StaffMessage, StaffReport, StaffTask
from .supervision import (
    category_of,
    direct_reports,
    rank_level,
    scope_label,
    staff_profile,
    visible_staff_ids,
)

User = get_user_model()


class StaffTaskSerializer(serializers.ModelSerializer):
    assigned_to_name = serializers.CharField(
        source="assigned_to.get_full_name", read_only=True
    )
    assigned_by_name = serializers.CharField(
        source="assigned_by.get_full_name", read_only=True
    )
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = StaffTask
        fields = "__all__"
        read_only_fields = ["school", "assigned_by", "completed_at"]


class StaffTaskViewSet(SchoolScopedViewSet):
    """Supervisors assign work; the assignee updates its status."""

    queryset = StaffTask.objects.select_related("assigned_to", "assigned_by").all()
    serializer_class = StaffTaskSerializer
    filterset_fields = ["status", "assigned_to", "assigned_by"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_superuser or user.role == "ADMIN":
            return qs
        return qs.filter(Q(assigned_to=user) | Q(assigned_by=user))

    def perform_create(self, serializer):
        user = self.request.user
        target = serializer.validated_data["assigned_to"]
        if target.id not in visible_staff_ids(user):
            raise PermissionDenied("You can only assign work to staff you supervise.")
        serializer.save(school=user.school, assigned_by=user)

    def perform_update(self, serializer):
        task = self.get_object()
        user = self.request.user
        is_admin = user.is_superuser or user.role == "ADMIN"
        is_owner = user.id == task.assigned_by_id
        is_assignee = user.id == task.assigned_to_id
        if not (is_admin or is_owner or is_assignee):
            raise PermissionDenied("Not your task.")

        if is_assignee and not (is_admin or is_owner):
            # The person doing the work reports progress; they don't get to
            # rewrite the brief or hand it to someone else.
            new_status = serializer.validated_data.get("status", task.status)
            task.status = new_status
            task.completed_at = (
                timezone.now() if new_status == StaffTask.Status.DONE else None
            )
            task.save(update_fields=["status", "completed_at", "updated_at"])
            serializer.instance = task
            return

        new_status = serializer.validated_data.get("status", task.status)
        serializer.save(
            completed_at=timezone.now() if new_status == StaffTask.Status.DONE else None
        )


class StaffMessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source="sender.get_full_name", read_only=True)

    class Meta:
        model = StaffMessage
        fields = "__all__"
        read_only_fields = ["school", "sender", "read_at"]


class StaffMessageViewSet(SchoolScopedViewSet):
    """Notes between a staff member and their supervisor."""

    queryset = StaffMessage.objects.select_related("sender", "recipient").all()
    serializer_class = StaffMessageSerializer

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset().filter(Q(sender=user) | Q(recipient=user))
        other = self.request.query_params.get("with")
        if other:
            try:
                other = int(other)
            except (TypeError, ValueError):
                raise ValidationError({"with": "Must be a staff user id."})
            qs = qs.filter(Q(sender_id=other) | Q(recipient_id=other))
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        recipient = serializer.validated_data["recipient"]
        _, profile = staff_profile(user)
        allowed = set(visible_staff_ids(user))
        if profile is not None and profile.supervisor_id:
            allowed.add(profile.supervisor_id)  # you may always message your own boss
        if recipient.id not in allowed:
            raise PermissionDenied("You can only message your supervisor or your team.")
        serializer.save(school=user.school, sender=user)


class MyTeamView(APIView):
    """GET /api/my-team/ — everyone I oversee, grouped by category."""

    def get(self, request):
        user = request.user
        ids = visible_staff_ids(user)
        direct = direct_reports(user)

        from .my_portal import _person

        # Two grouped counts instead of two queries per person.
        open_tasks = dict(
            StaffTask.objects.filter(assigned_to_id__in=ids, status__in=["OPEN", "DOING"])
            .values_list("assigned_to_id")
            .annotate(n=Count("id"))
        )
        pending_reports = dict(
            StaffReport.objects.filter(
                author_id__in=ids, status=StaffReport.Status.SUBMITTED
            )
            .values_list("author_id")
            .annotate(n=Count("id"))
        )

        accounts = (
            User.objects.filter(id__in=ids)
            .select_related("teacher_profile", "support_profile")
            .order_by("first_name", "username")
        )
        groups = {}
        for account in accounts:
            person = _person(account, request)
            person["direct"] = account.id in direct
            person["open_tasks"] = open_tasks.get(account.id, 0)
            person["pending_reports"] = pending_reports.get(account.id, 0)
            groups.setdefault(category_of(account), []).append(person)

        return Response(
            {
                "scope": scope_label(user),
                "rank_level": rank_level(user),
                "total": len(ids),
                "groups": [
                    {"category": name, "staff": people}
                    for name, people in sorted(groups.items())
                ],
            }
        )


class TeamMemberView(APIView):
    """GET /api/my-team/<user_id>/ — one team member: profile, their reports,
    their assigned work, and our message thread."""

    def get(self, request, user_id):
        user = request.user
        # visible_staff_ids already grants admins the whole school — and stops
        # at the school border, which a blanket admin bypass would not.
        if user_id not in visible_staff_ids(user):
            raise PermissionDenied("This staff member is not in your team.")

        account = User.objects.filter(id=user_id).first()
        if account is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        from .my_portal import StaffReportSerializer, _person
        from .supervision import staff_profile

        kind, profile = staff_profile(account)
        reports = StaffReport.objects.filter(author=account).order_by("-created_at")
        tasks = StaffTask.objects.filter(assigned_to=account)
        thread = StaffMessage.objects.filter(
            Q(sender=user, recipient=account) | Q(sender=account, recipient=user)
        )
        # Reading the thread marks their notes to me as seen.
        thread.filter(recipient=user, read_at__isnull=True).update(read_at=timezone.now())

        responsibilities = []
        if profile is not None:
            from apps.facilities.models import FacilityAssignment

            key = {"teacher": profile} if kind == "TEACHING" else {"support_staff": profile}
            responsibilities = [
                f"{a.position} — {a.facility.name}"
                for a in FacilityAssignment.objects.filter(**key).select_related("facility")
            ]
            responsibilities += [d.title for d in account.duties.all()]

        return Response(
            {
                "person": _person(account, request),
                "category": category_of(account),
                "responsibilities": responsibilities,
                "reports": StaffReportSerializer(
                    reports, many=True, context={"request": request}
                ).data,
                "tasks": StaffTaskSerializer(
                    tasks, many=True, context={"request": request}
                ).data,
                "messages": StaffMessageSerializer(
                    thread, many=True, context={"request": request}
                ).data,
            }
        )
