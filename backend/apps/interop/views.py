"""KEMIS/NEMIS-shaped exports so MoE returns are one click, not re-keying.

Column layouts follow the learner-register shape KEMIS uses; adjust headers
here (single integration point) when MoE publishes formal specs or an API.
"""

import csv

from django.db.models import Count
from django.http import HttpResponse
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.students.models import Learner


def _require_office(user):
    """MoE returns are an office job. These exports carry every learner's name,
    UPI and date of birth — minors' data under the Kenya DPA 2019 — so they are
    not something a parent or a class teacher's login should be able to pull.
    """
    if not (user.is_superuser or user.role == "ADMIN"):
        raise PermissionDenied("Only the school admin can export MoE returns.")
    if user.school_id is None and not user.is_superuser:
        raise PermissionDenied("This account is not attached to a school.")


@api_view(["GET"])
def kemis_learners_csv(request):
    _require_office(request.user)
    learners = (
        Learner.objects.filter(school=request.user.school, active=True)
        .select_related("pathway", "school")
        .order_by("grade", "admission_number")
    )

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="kemis_learner_register.csv"'
    writer = csv.writer(response)
    writer.writerow(
        ["UPI", "AdmissionNo", "Surname", "FirstName", "MiddleName", "DOB", "Gender",
         "Grade", "Pathway", "SchoolCode", "KemisCode"]
    )
    for l in learners:
        writer.writerow(
            [l.upi, l.admission_number, l.last_name, l.first_name, l.middle_name,
             l.date_of_birth.isoformat(), l.gender, l.grade,
             l.pathway.code if l.pathway else "", l.school.code, l.school.kemis_code]
        )
    return response


@api_view(["GET"])
def kemis_enrollment(request):
    """Enrollment counts by grade and gender — the numbers MoE returns ask for."""
    _require_office(request.user)
    counts = (
        Learner.objects.filter(school=request.user.school, active=True)
        .values("grade", "gender")
        .annotate(count=Count("id"))
        .order_by("grade", "gender")
    )
    by_grade = {}
    for row in counts:
        grade = by_grade.setdefault(row["grade"], {"M": 0, "F": 0, "total": 0})
        grade[row["gender"]] = row["count"]
        grade["total"] += row["count"]

    from apps.schools.structure import GRADE_LABELS

    rows = [
        {
            "grade": grade,
            "label": GRADE_LABELS.get(grade, f"Grade {grade}"),
            "male": totals["M"],
            "female": totals["F"],
            "total": totals["total"],
        }
        for grade, totals in sorted(by_grade.items())
    ]
    return Response(
        {
            "school": request.user.school.code,
            "rows": rows,
            "totals": {
                "male": sum(r["male"] for r in rows),
                "female": sum(r["female"] for r in rows),
                "total": sum(r["total"] for r in rows),
            },
            # Kept for existing callers of the original shape.
            "enrollment": by_grade,
        }
    )
