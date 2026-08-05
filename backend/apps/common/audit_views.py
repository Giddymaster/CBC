"""Reading the audit log. Read-only by construction — see apps/common/audit.py."""

from rest_framework import serializers, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from .audit import AuditEntry


class AuditEntrySerializer(serializers.ModelSerializer):
    action_label = serializers.CharField(source="get_action_display", read_only=True)

    class Meta:
        model = AuditEntry
        fields = [
            "id", "created_at", "actor", "actor_name", "action", "action_label",
            "target_type", "target_id", "label", "detail",
        ]


class AuditEntryViewSet(viewsets.ReadOnlyModelViewSet):
    """GET only. There is no write endpoint anywhere — a log an admin can edit
    is not evidence of anything."""

    serializer_class = AuditEntrySerializer
    filterset_fields = ["action", "actor", "target_type"]
    search_fields = ["label", "actor_name"]

    def get_queryset(self):
        user = self.request.user
        if not (user.is_superuser or user.role == "ADMIN"):
            raise PermissionDenied("Only the school admin can read the audit log.")
        qs = AuditEntry.objects.select_related("actor")
        if user.is_superuser and user.school_id is None:
            return qs
        return qs.filter(school_id=user.school_id)


class AuditSummaryView(APIView):
    """GET /api/audit/summary/ — what kinds of thing have been happening."""

    def get(self, request):
        user = request.user
        if not (user.is_superuser or user.role == "ADMIN"):
            raise PermissionDenied("Only the school admin can read the audit log.")

        from django.db.models import Count

        qs = AuditEntry.objects.filter(school_id=user.school_id)
        rows = qs.values("action").annotate(n=Count("id")).order_by("-n")
        labels = dict(AuditEntry.Action.choices)
        return Response(
            {
                "total": qs.count(),
                "actions": [
                    {
                        "action": row["action"],
                        "label": labels.get(row["action"], row["action"]),
                        "count": row["n"],
                    }
                    for row in rows
                ],
            }
        )
