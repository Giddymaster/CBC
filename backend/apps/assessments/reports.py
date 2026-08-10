"""Report-card data assembly — one builder shared by the JSON API and the PDF
renderer, so the two can never drift apart."""

from decimal import Decimal


def _fees(learner, term, year):
    """What the family owes on this report, and what the next term will cost.

    A Kenyan report form carries the fee balance and the coming term's fee —
    it is how the school tells a parent, in the one document they always read,
    what to bring on opening day.
    """
    from apps.payments.models import FeeStructure, Invoice

    # term and year arrive as query-string text on the API path.
    try:
        term = int(term) if term else None
        year = int(year) if year else None
    except (TypeError, ValueError):
        term = year = None

    invoices = Invoice.objects.filter(learner=learner).select_related("fee_structure")
    if term:
        invoices = invoices.filter(fee_structure__term=term)
    if year:
        invoices = invoices.filter(fee_structure__year=year)

    billed = paid = Decimal("0")
    for invoice in invoices:
        billed += invoice.amount_due
        paid += invoice.amount_paid

    # Next term rolls into the new year after Term 3.
    next_term, next_year = None, None
    if term and year:
        next_term, next_year = (1, year + 1) if term >= 3 else (term + 1, year)
    upcoming = (
        FeeStructure.objects.filter(
            school=learner.school, grade=learner.grade,
            term=next_term, year=next_year,
        ).first()
        if next_term
        else None
    )
    # Arrears follow the child, so the coming term's demand is the new fee
    # plus whatever is still owed.
    balance = billed - paid
    return {
        "billed": str(billed),
        "paid": str(paid),
        "balance": str(balance),
        "next_term": next_term,
        "next_year": next_year,
        "next_term_fee": str(upcoming.amount) if upcoming else None,
        "next_term_breakdown": (upcoming.breakdown or {}) if upcoming else {},
        "next_term_total_due": (
            str(upcoming.amount + balance) if upcoming else None
        ),
    }


def build_report_card(learner, term=None, year=None) -> dict:
    scores = learner.scores.select_related("assessment__learning_area")
    if term:
        scores = scores.filter(assessment__term=term)
    if year:
        scores = scores.filter(assessment__year=year)

    by_area = {}
    for score in scores:
        area = score.assessment.learning_area.name
        by_area.setdefault(area, {})[score.assessment.kind] = {
            "marks": float(score.marks),
            "max_marks": score.assessment.max_marks,
            "competency_level": score.competency_level,
            "comment": score.comment,
        }

    return {
        "learner": {
            "id": learner.id,
            "name": learner.full_name,
            "admission_number": learner.admission_number,
            "upi": learner.upi,
            "grade": learner.grade,
            "stream": learner.stream,
            "pathway": learner.pathway.get_code_display() if learner.pathway else None,
        },
        "school": {
            "name": learner.school.name,
            "code": learner.school.code,
            "county": learner.school.county,
        },
        "term": term,
        "year": year,
        "learning_areas": by_area,
        "fees": _fees(learner, term, year),
    }
