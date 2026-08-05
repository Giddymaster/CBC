"""Report-card data assembly — one builder shared by the JSON API and the PDF
renderer, so the two can never drift apart."""


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
    }
