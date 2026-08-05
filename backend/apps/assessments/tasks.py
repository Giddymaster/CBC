"""Celery tasks: batch report-card PDF generation for a whole class."""

from pathlib import Path

from celery import shared_task
from django.conf import settings


@shared_task
def generate_class_report_cards(school_id: int, grade: int, stream: str, term: int, year: int):
    """Render every active learner's report card to MEDIA_ROOT/report_cards/...
    Returns the list of generated file paths (relative to MEDIA_ROOT)."""
    from apps.students.models import Learner

    from .pdf import render_report_card_pdf
    from .reports import build_report_card

    out_dir = Path(settings.MEDIA_ROOT) / "report_cards" / str(year) / f"T{term}"
    out_dir.mkdir(parents=True, exist_ok=True)

    generated = []
    learners = Learner.objects.filter(
        school_id=school_id, grade=grade, stream=stream, active=True
    ).select_related("pathway", "school")
    for learner in learners:
        data = build_report_card(learner, term=term, year=year)
        pdf_bytes = render_report_card_pdf(data)
        filename = f"{learner.admission_number}.pdf"
        (out_dir / filename).write_bytes(pdf_bytes)
        generated.append(f"report_cards/{year}/T{term}/{filename}")
    return generated
