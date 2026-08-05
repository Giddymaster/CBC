"""Smoke test for the teacher portal: summary payload + bulk score entry.
Run: python manage.py shell -c "exec(open('scripts/smoke_test3.py').read())"
"""

from django.conf import settings
from rest_framework.test import APIClient

settings.ALLOWED_HOSTS.append("testserver")

from apps.accounts.models import User
from apps.assessments.models import Assessment, Score
from apps.schools.models import School

school = School.objects.get(code="12345678")
client = APIClient()
client.force_authenticate(User.objects.get(username="mwalimu"))

# 1. Teacher summary
print("--- Teacher summary ---")
res = client.get("/api/teacher/summary/")
assert res.status_code == 200, res.status_code
data = res.json()
print(f"  {data['teacher']['name']} (TSC {data['teacher']['tsc_number']})")
print(f"  Timetable lessons: {len(data['timetable'])}")
assert len(data["timetable"]) == 9, "expected 5 math + 4 science lessons"
labels = [a["label"] for a in data["assessments"]]
print(f"  Assessments visible: {labels}")
assert any("CAT 1" in l for l in labels) and any("CAT 2" in l for l in labels)
assert len(data["schemes_of_work"]) == 1
print(f"  Schemes: {len(data['schemes_of_work'])}, announcements: {len(data['announcements'])}")

# 2. Bulk score entry with derivation, validation, and idempotent replay
print("--- Bulk score entry ---")
cat2 = Assessment.objects.get(school=school, kind="CAT2", year=2026)
learners = list(school.learners.order_by("admission_number").values_list("pk", flat=True))
payload = {
    "assessment": cat2.id,
    "records": [
        {"learner": learners[0], "marks": 45},   # 90% -> EE
        {"learner": learners[1], "marks": 24},   # 48% -> AE
        {"learner": learners[2], "marks": 99},   # > max_marks (50) -> skipped
        {"learner": 999999, "marks": 30},        # unknown learner -> skipped
    ],
}
res = client.post("/api/scores/bulk/", payload, format="json",
                  headers={"Idempotency-Key": "score-bulk-test-1"})
assert res.status_code == 200, res.content
body = res.json()
levels = {s["learner"]: s["competency_level"] for s in body["saved"]}
print(f"  Saved: {body['saved']}")
print(f"  Skipped (invalid): {body['skipped']}")
assert levels[learners[0]] == "EE" and levels[learners[1]] == "AE"
assert set(body["skipped"]) == {learners[2], 999999}
assert Score.objects.filter(assessment=cat2).count() == 2

# replay with same key must not re-write and must return stored response
res2 = client.post("/api/scores/bulk/", payload, format="json",
                   headers={"Idempotency-Key": "score-bulk-test-1"})
assert res2.headers.get("X-Idempotent-Replay") == "true"
assert Score.objects.filter(assessment=cat2).count() == 2
print("  Replay with same Idempotency-Key returned stored response, no double-write")

# upsert: corrected mark overwrites, level re-derived
payload2 = {"assessment": cat2.id, "records": [{"learner": learners[1], "marks": 40}]}
res3 = client.post("/api/scores/bulk/", payload2, format="json")
assert res3.json()["saved"][0]["competency_level"] == "EE"  # 80%
assert Score.objects.filter(assessment=cat2).count() == 2
print("  Corrected mark upserted (24 -> 40, AE -> EE), still one row per learner")

print("\nTEACHER PORTAL SMOKE TESTS PASSED")
