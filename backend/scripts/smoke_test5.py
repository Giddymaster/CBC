"""Smoke test: school structure, grade drill-down, student profile.
Run: python manage.py shell -c "exec(open('scripts/smoke_test5.py').read())"
"""

from django.conf import settings
from rest_framework.test import APIClient

settings.ALLOWED_HOSTS.append("testserver")

from apps.accounts.models import User

admin = APIClient(); admin.force_authenticate(User.objects.get(username="admin"))
parent = APIClient(); parent.force_authenticate(User.objects.get(username="mzazi"))

# 1. Structure: three categories, PP1..G12, counts land on G7
print("--- School structure ---")
res = admin.get("/api/school/structure/")
assert res.status_code == 200, res.content
data = res.json()
names = [c["name"] for c in data["categories"]]
assert names == ["Primary", "Junior School", "Senior School"]
primary = data["categories"][0]["grades"]
assert primary[0]["label"] == "PP1" and primary[1]["label"] == "PP2"
g7 = next(g for c in data["categories"] for g in c["grades"] if g["grade"] == 7)
print(f"  Categories: {names}")
print(f"  Primary grades: {[g['label'] for g in primary]}")
print(f"  G7: {g7['total']} learners ({g7['male']}M/{g7['female']}F), classes: {g7['classes']}")
assert g7["total"] == 5 and g7["male"] == 2 and g7["female"] == 3
assert g7["classes"][0]["class_teacher"] == "Juma Mwalimu"

# Parents may not see the structure
assert parent.get("/api/school/structure/").status_code == 403
print("  Parent blocked from structure (403)")

# 2. Grade detail: students + attendance today, class teacher panel, timetable
print("--- Grade 7 detail ---")
res = admin.get("/api/school/grades/7/")
assert res.status_code == 200, res.content
detail = res.json()
totals = detail["totals"]
print(f"  Totals: {totals}")
assert totals["students"] == 5

ct = detail["class_teachers"][0]
print(f"  Class teacher {ct['stream']}: {ct['name']} (TSC {ct['tsc_number']}), "
      f"present={ct['present_today']}, roll_call_taken={ct['roll_call_taken_today']}")
print(f"  Subjects: {ct['subjects']}; schemes: {len(ct['schemes_of_work'])}; "
      f"timetable lessons: {len(ct['timetable'])}")
assert ct["name"] == "Juma Mwalimu"
assert ct["present_today"] == "P"
assert set(ct["subjects"]) == {"Mathematics", "Integrated Science"}
assert len(ct["timetable"]) == 9

assert len(detail["timetable"]) == 18, "grade timetable should show all 18 lessons"
first = detail["timetable"][0]
print(f"  Grade timetable first slot: day {first['day']} P{first['period']} "
      f"{first['learning_area']} ({first['teacher']})")

# PP1 (negative grade) URL resolves
assert admin.get("/api/school/grades/-1/").status_code == 200
print("  PP1 (grade=-1) endpoint OK (empty grade)")

# 3. Student profile: scores, guardian, fees, attendance
print("--- Student profile ---")
learner_id = detail["students"][0]["id"]
res = admin.get(f"/api/learners/{learner_id}/profile/")
assert res.status_code == 200, res.content
profile = res.json()
rc = profile["report_card"]
print(f"  {rc['learner']['name']}: areas={list(rc['learning_areas'].keys())}")
print(f"  Guardian: {profile['guardians'][0]['full_name']} {profile['guardians'][0]['phone']}")
print(f"  Fees balance: KES {profile['fees']['total_balance']}; "
      f"attendance: {profile['attendance']['present']}P/{profile['attendance']['absent']}A")
assert profile["guardians"][0]["phone"]
assert "Mathematics" in rc["learning_areas"]

# Parent can see own child's profile but not others
own_child = User.objects.get(username="mzazi").guardian_profile.learners.first()
assert parent.get(f"/api/learners/{own_child.id}/profile/").status_code == 200
other = [s for s in detail["students"] if s["id"] != own_child.id][0]
assert parent.get(f"/api/learners/{other['id']}/profile/").status_code == 403
print("  Parent: own child 200, other child 403")

print("\nSCHOOL STRUCTURE SMOKE TESTS PASSED")
