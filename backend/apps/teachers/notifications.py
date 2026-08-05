"""What is waiting for me right now.

One endpoint behind the bell in the topbar. It answers a single question — is
there anything I need to look at? — across the four things that arrive
unannounced: a note from my supervisor, work assigned to me, a report waiting
on my approval, and a report of mine that was sent back.
"""

from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import StaffMessage, StaffReport, StaffTask


def _when(value):
    return value.isoformat() if value else None


class NotificationsView(APIView):
    """GET /api/notifications/ — unread items for the signed-in staff member."""

    def get(self, request):
        user = request.user
        items = []

        messages = (
            StaffMessage.objects.filter(recipient=user, read_at__isnull=True)
            .select_related("sender")
            .order_by("-created_at")[:20]
        )
        for message in messages:
            sender = message.sender
            items.append(
                {
                    "id": f"msg-{message.id}",
                    "kind": "MESSAGE",
                    "title": f"Message from {sender.get_full_name() or sender.username}",
                    "body": message.body,
                    "from_id": sender.id,
                    "at": _when(message.created_at),
                }
            )

        tasks = (
            StaffTask.objects.filter(assigned_to=user, status=StaffTask.Status.OPEN)
            .select_related("assigned_by")
            .order_by("-created_at")[:20]
        )
        today = timezone.localdate()
        for task in tasks:
            by = task.assigned_by
            overdue = bool(task.due_date and task.due_date < today)
            items.append(
                {
                    "id": f"task-{task.id}",
                    "kind": "TASK",
                    "title": f"New work from {by.get_full_name() or by.username}",
                    "body": task.title,
                    "from_id": by.id,
                    "due_date": task.due_date,
                    "overdue": overdue,
                    "priority": task.priority,
                    "at": _when(task.created_at),
                }
            )

        to_review = (
            StaffReport.objects.filter(
                supervisor=user, status=StaffReport.Status.SUBMITTED
            )
            .select_related("author")
            .order_by("-submitted_at")[:20]
        )
        for report in to_review:
            author = report.author
            items.append(
                {
                    "id": f"review-{report.id}",
                    "kind": "REVIEW",
                    "title": f"{author.get_full_name() or author.username} submitted a report",
                    "body": report.title,
                    "from_id": author.id,
                    "at": _when(report.submitted_at or report.created_at),
                }
            )

        returned = StaffReport.objects.filter(
            author=user, status=StaffReport.Status.RETURNED
        ).order_by("-reviewed_at")[:20]
        for report in returned:
            items.append(
                {
                    "id": f"returned-{report.id}",
                    "kind": "RETURNED",
                    "title": "A report was returned for changes",
                    "body": f"{report.title} — {report.review_comment}".strip(" —"),
                    "at": _when(report.reviewed_at),
                }
            )

        items.sort(key=lambda row: row["at"] or "", reverse=True)
        return Response(
            {
                "count": len(items),
                "unread_messages": len(messages),
                "items": items,
            }
        )

    def post(self, request):
        """Mark message notifications as read.

        Only messages carry a read state — a task or a pending review stays in
        the list until the work itself is done, which is the honest signal.
        """
        StaffMessage.objects.filter(recipient=request.user, read_at__isnull=True).update(
            read_at=timezone.now()
        )
        return Response({"ok": True})
