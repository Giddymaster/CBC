"""Smoke test: scheme-of-work upload, AI generation (stub mode), and review.
Run: python manage.py shell -c "exec(open('scripts/smoke_test4.py').read())"
"""

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

settings.ALLOWED_HOSTS.append("testserver")

from apps.accounts.models import User
from apps.assessments.models import LearningArea
from apps.teachers.models import SchemeOfWork

teacher_client = APIClient()
teacher_client.force_authenticate(User.objects.get(username="mwalimu"))
admin_client = APIClient()
admin_client.force_authenticate(User.objects.get(username="admin"))

math = LearningArea.objects.get(code="MATH")
english = LearningArea.objects.get(code="ENG")

# 1. Teacher uploads a scheme document -> PENDING, source UPLOADED
print("--- Upload ---")
doc = SimpleUploadedFile("scheme_t3.pdf", b"%PDF-1.4 fake scheme doc", content_type="application/pdf")
res = teacher_client.post(
    "/api/schemes-of-work/",
    {"learning_area": english.id, "grade": 7, "term": 3, "year": 2026, "document": doc},
    format="multipart",
)
assert res.status_code == 201, res.content
uploaded = res.json()
print(f"  Uploaded scheme #{uploaded['id']}: status={uploaded['status']}, "
      f"source={uploaded['source']}, doc={uploaded['document']}")
assert uploaded["status"] == "PENDING" and uploaded["source"] == "UPLOADED"
assert uploaded["document"], "document URL missing"
assert uploaded["teacher_name"] == "Juma Mwalimu", "teacher not auto-attached"

# 2. Teacher generates a scheme with AI (stub mode, no API key needed)
print("--- AI generate (stub mode) ---")
res = teacher_client.post(
    "/api/schemes-of-work/generate/",
    {"learning_area": math.id, "grade": 7, "term": 3, "year": 2026,
     "weeks": 3, "lessons_per_week": 2},
    format="json",
)
assert res.status_code == 201, res.content
generated = res.json()
weeks = generated["content"]["weeks"]
print(f"  Generated scheme #{generated['id']}: status={generated['status']}, "
      f"source={generated['source']}, {len(weeks)} weeks x {len(weeks[0]['lessons'])} lessons")
print(f"  Generator: {generated['content']['generator']}")
assert generated["status"] == "PENDING" and generated["source"] == "GENERATED"
assert len(weeks) == 3 and len(weeks[0]["lessons"]) == 2
assert weeks[0]["lessons"][0]["learning_outcomes"], "missing learning outcomes"

# 3. Teacher cannot review; admin can
print("--- Review permissions & decisions ---")
res = teacher_client.post(
    f"/api/schemes-of-work/{generated['id']}/review/",
    {"decision": "approve"}, format="json",
)
assert res.status_code == 403, f"teacher was allowed to review! {res.status_code}"
print("  Teacher blocked from reviewing (403)")

res = admin_client.post(
    f"/api/schemes-of-work/{generated['id']}/review/",
    {"decision": "approve", "comment": "Well structured, proceed."}, format="json",
)
assert res.status_code == 200, res.content
approved = res.json()
print(f"  Admin approved #{approved['id']}: status={approved['status']}, "
      f"by={approved['reviewed_by_name']}")
assert approved["status"] == "APPROVED" and approved["reviewed_by_name"] is not None

res = admin_client.post(
    f"/api/schemes-of-work/{uploaded['id']}/review/",
    {"decision": "reject", "comment": "Please align week 4 with the KICD design."},
    format="json",
)
assert res.status_code == 200 and res.json()["status"] == "REJECTED"
print(f"  Admin rejected #{uploaded['id']} with comment")

# 4. Admin sees pending queue via filter; teacher summary reflects statuses
res = admin_client.get("/api/schemes-of-work/?status=PENDING")
pending_count = res.json()["count"]
res = teacher_client.get("/api/teacher/summary/")
statuses = {s["id"]: s["status"] for s in res.json()["schemes_of_work"]}
print(f"  Pending queue size now: {pending_count}; teacher sees statuses {sorted(set(statuses.values()))}")
assert statuses[generated["id"]] == "APPROVED" and statuses[uploaded["id"]] == "REJECTED"

# 5. AI real-mode wiring is present but inactive without a key
import os

from apps.teachers.services.ai_scheme import _ai_configured

assert _ai_configured() == bool(os.getenv("ANTHROPIC_API_KEY"))
print(f"  AI mode: {'Claude API' if _ai_configured() else 'stub (set ANTHROPIC_API_KEY to enable)'}")

print("\nSCHEME WORKFLOW SMOKE TESTS PASSED")
