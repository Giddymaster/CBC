"""Parent portal: one endpoint returning everything the parent PWA needs —
their children, fee balances, current-year report cards, and announcements."""

from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.assessments.reports import build_report_card
from apps.communication.models import Announcement
from apps.payments.models import Invoice


class ParentSummaryView(APIView):
    def get(self, request):
        guardian = getattr(request.user, "guardian_profile", None)
        if guardian is None:
            return Response(
                {"detail": "This account is not linked to a guardian profile."}, status=403
            )

        year = int(request.query_params.get("year", timezone.now().year))
        children = []
        for learner in guardian.learners.filter(active=True).select_related("pathway", "school"):
            invoices = Invoice.objects.filter(learner=learner)
            balance = sum((inv.balance for inv in invoices), start=0)
            children.append(
                {
                    # Identity at the top level so the PWA can key and link on it
                    # without reaching into the report card.
                    "id": learner.id,
                    "name": learner.full_name,
                    "admission_number": learner.admission_number,
                    "grade": learner.grade,
                    "stream": learner.stream,
                    "report_card": build_report_card(learner, year=year),
                    "fees": {
                        "total_balance": str(balance),
                        "invoices": [
                            {
                                "id": inv.id,
                                "due": str(inv.amount_due),
                                "paid": str(inv.amount_paid),
                                "balance": str(inv.balance),
                                "status": inv.status,
                            }
                            for inv in invoices
                        ],
                    },
                }
            )

        announcements = Announcement.objects.filter(
            school=guardian.school,
            audience__in=[Announcement.Audience.ALL, Announcement.Audience.PARENTS],
        ).order_by("-created_at")[:10]

        return Response(
            {
                "guardian": {"name": guardian.full_name, "phone": guardian.phone},
                "school": guardian.school.name,
                "year": year,
                "children": children,
                "announcements": [
                    {
                        "id": a.id,
                        "title": a.title,
                        "body": a.body,
                        "meeting_link": a.meeting_link,
                        "date": a.created_at.date().isoformat(),
                    }
                    for a in announcements
                ],
            }
        )
