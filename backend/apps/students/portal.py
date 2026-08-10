"""Parent portal: one endpoint returning everything the parent PWA needs —
their children, fee balances, current-year report cards, and announcements."""

from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.assessments.reports import build_report_card
from apps.communication.models import Announcement
from apps.payments.models import Invoice


def _class_teacher_of(learner):
    """The teacher a parent should ask for by name."""
    from apps.students.models import ClassGroup

    group = ClassGroup.objects.filter(
        school=learner.school, grade=learner.grade, stream=learner.stream,
        class_teacher__isnull=False,
    ).select_related("class_teacher__user").first()
    if group is None:
        return None
    user = group.class_teacher.user
    return user.get_full_name() or user.username


class ParentSummaryView(APIView):
    def get(self, request):
        guardian = getattr(request.user, "guardian_profile", None)
        if guardian is None:
            return Response(
                {"detail": "This account is not linked to a guardian profile."}, status=403
            )

        year = int(request.query_params.get("year", timezone.now().year))
        term = request.query_params.get("term")
        children = []
        for learner in guardian.learners.filter(active=True).select_related("pathway", "school"):
            invoices = Invoice.objects.filter(learner=learner).select_related(
                "fee_structure"
            )
            balance = sum((inv.balance for inv in invoices), start=0)
            report = build_report_card(learner, term=term, year=year)
            children.append(
                {
                    # Identity at the top level so the PWA can key and link on it
                    # without reaching into the report card.
                    "id": learner.id,
                    "name": learner.full_name,
                    "admission_number": learner.admission_number,
                    "grade": learner.grade,
                    "stream": learner.stream,
                    # The child's own page: who they are on the register.
                    "profile": {
                        "upi": learner.upi,
                        "date_of_birth": (
                            learner.date_of_birth.isoformat()
                            if learner.date_of_birth else None
                        ),
                        "gender": learner.get_gender_display(),
                        "admission_date": (
                            learner.admission_date.isoformat()
                            if learner.admission_date else None
                        ),
                        "pathway": (
                            learner.pathway.get_code_display()
                            if learner.pathway else None
                        ),
                        "photo": (
                            request.build_absolute_uri(learner.photo.url)
                            if learner.photo else None
                        ),
                        "class_teacher": _class_teacher_of(learner),
                    },
                    "report_card": report,
                    "fees": {
                        "total_balance": str(balance),
                        # What this term costs and what the next one will —
                        # the two numbers a parent opens the app for.
                        **report["fees"],
                        "invoices": [
                            {
                                "id": inv.id,
                                "term": inv.fee_structure.term,
                                "year": inv.fee_structure.year,
                                "breakdown": inv.fee_structure.breakdown or {},
                                "due": str(inv.amount_due),
                                "paid": str(inv.amount_paid),
                                "balance": str(inv.balance),
                                "status": inv.status,
                                "payments": [
                                    {
                                        "amount": str(p.amount),
                                        "method": p.get_method_display(),
                                        "paid_on": p.paid_on.isoformat(),
                                        "reference": p.reference,
                                    }
                                    for p in inv.payments.all()
                                ],
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
