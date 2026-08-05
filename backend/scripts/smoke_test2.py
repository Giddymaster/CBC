"""Smoke test for next-steps features: PDF report cards, parent portal,
timetable generation.
Run: python manage.py shell -c "exec(open('scripts/smoke_test2.py').read())"
"""

from collections import defaultdict

from apps.assessments.pdf import render_report_card_pdf
from apps.assessments.reports import build_report_card
from apps.assessments.tasks import generate_class_report_cards
from apps.schools.models import School
from apps.students.models import Learner
from apps.timetable.generator import generate_timetable
from apps.timetable.models import Lesson, LessonRequirement

school = School.objects.get(code="12345678")

# 1. PDF report card
print("--- PDF report cards ---")
learner = Learner.objects.get(school=school, admission_number="ADM002")
pdf = render_report_card_pdf(build_report_card(learner, term=2, year=2026))
assert pdf.startswith(b"%PDF"), "not a PDF!"
print(f"  Single PDF rendered: {len(pdf):,} bytes")

files = generate_class_report_cards(school.id, 7, "North", 2, 2026)
assert len(files) == 5, files
print(f"  Class batch task generated {len(files)} PDFs -> media/{files[0].rsplit('/', 1)[0]}/")

# 2. Parent portal (exercise the view logic through the linked guardian)
print("--- Parent portal ---")
from apps.accounts.models import User

parent = User.objects.get(username="mzazi")
guardian = parent.guardian_profile
assert guardian is not None
children = list(guardian.learners.filter(active=True))
assert len(children) == 1 and children[0].admission_number == "ADM001"
report = build_report_card(children[0], year=2026)
assert "Mathematics" in report["learning_areas"]
balance = sum((inv.balance for inv in children[0].invoices.all()), start=0)
print(f"  mzazi -> {children[0].full_name}: fee balance KES {balance}, "
      f"{len(report['learning_areas'])} learning area(s) on report")

# 3. Timetable generation
print("--- Timetable generation ---")
result = generate_timetable(school)
reqs = LessonRequirement.objects.filter(school=school)
expected = sum(r.lessons_per_week for r in reqs)
print(f"  Placed {result['placed']}/{expected} lessons "
      f"({result['slots_available']} slots), unplaced: {result['unplaced']}")
assert result["placed"] == expected and not result["unplaced"]

# No clashes: teacher, class, and lab must each be unique per slot.
teacher_slots, class_slots, lab_slots = defaultdict(int), defaultdict(int), defaultdict(int)
science_days = set()
for lesson in Lesson.objects.filter(school=school):
    teacher_slots[(lesson.day, lesson.period_id, lesson.teacher_id)] += 1
    class_slots[(lesson.day, lesson.period_id, lesson.grade, lesson.stream)] += 1
    if lesson.room_id:
        lab_slots[(lesson.day, lesson.period_id, lesson.room_id)] += 1
    if lesson.learning_area.code == "INT-SCI":
        science_days.add(lesson.day)
assert all(v == 1 for v in teacher_slots.values()), "teacher double-booked!"
assert all(v == 1 for v in class_slots.values()), "class double-booked!"
assert all(v == 1 for v in lab_slots.values()), "lab double-booked!"
assert len(science_days) == 4, f"science not spread across days: {science_days}"
print(f"  No teacher/class/lab clashes; science lab lessons spread over {len(science_days)} days")

print("\nALL NEXT-STEP SMOKE TESTS PASSED")
