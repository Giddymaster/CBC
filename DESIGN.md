# CBC School Management System — Kenya

**Version 2** — incorporates payments (M-Pesa), offline tolerance, and KEMIS/NEMIS interoperability as first-class modules, on the finalized tech stack.

## Tech Stack (final)

| Layer | v1 (build now) | Later (when scale demands) |
|---|---|---|
| Infrastructure | AWS `af-south-1` (modest: Lightsail/ECS + RDS) + Cloudflare | Scale out, multi-region |
| Backend | Django + DRF + PostgreSQL + Redis + Celery | — |
| Frontend | React (web) + PWA parent portal | Flutter native apps |
| Payments | **M-Pesa (Safaricom Daraja API)** — STK Push + C2B reconciliation | Card/bank rails |
| Communication | Africa's Talking SMS + WhatsApp Business API; meeting deep-links (Zoom/Meet) | Embedded video SDK |
| Analytics | Metabase (open-source) on PostgreSQL | ML once 2–3 terms of data exist |
| Security | Django auth + django-allauth (Google Workspace for Education), Cloudflare Zero Trust for admin surfaces | SSO/Cognito if enterprise demand |

**Compliance note:** register as a data controller under the Kenya Data Protection Act 2019 (learner data = minors' data). Closest AWS region is Cape Town (`af-south-1`); Cloudflare fronts it for Nairobi-level latency.

## Architecture decisions

- **Multi-tenancy: shared tables, row-scoped by `school` FK.** Every tenant-owned model inherits `SchoolScopedModel`. Simplest to operate, easy cross-school analytics for MoE reporting, and a clean migration path to schema-per-school only if a mega-tenant ever demands it. All API queries are filtered by the authenticated user's school.
- **One language on the backend (Python).** Web team and future analytics/ML share Django's ORM and the same models.
- **SQLite in dev, PostgreSQL in prod** via `DATABASE_URL`-style env config. No local Postgres needed to contribute.
- **Celery + Redis** for anything slow or bursty: SMS blasts, report-card PDF generation, timetable solving, M-Pesa reconciliation.

## Core Modules

1. **Student Information System** (`apps/students`) — learner profiles (UPI), CBC pathway assignment (STEM, Social Sciences, Arts & Sports Science), grade/stream, guardians with phone numbers (the SMS/M-Pesa anchor).
2. **Teacher Management** (`apps/teachers`) — TSC number, subjects, schemes of work, lesson plans, professional development log.
3. **Assessment Engine** (`apps/assessments`) — CAT1/CAT2/End-Term + formative assessments, score entry, **automatic competency-level derivation (EE/ME/AE/BE)** from CBC rubric bands, report card endpoint.
4. **Timetable** (`apps/timetable`) — rooms, periods, lessons with **clash validation** (teacher/room/stream double-booking rejected at write time). Auto-generation is a later Celery job; the data model supports it now.
5. **Communication Hub** (`apps/communication`) — Africa's Talking SMS (graceful no-op stub without API keys), announcements, message log. WhatsApp Business API behind the same service interface. Video = deep-links, not embedded SDKs.
6. **Attendance Register** (`apps/attendance`) — daily learner/teacher roll-call, **offline-tolerant** (see below).
7. **Payments / Fees** (`apps/payments`) — fee structures per grade/term, invoices, **M-Pesa Daraja STK Push**, C2B confirmation webhook, automatic invoice reconciliation by account reference.
8. **Interoperability** (`apps/interop`) — KEMIS/NEMIS-shaped CSV/JSON exports (learner register, enrollment summary) so MoE returns are one click, not a re-keying exercise.

## The 3 previously-missing pieces (now designed in)

### 1. Payments — M-Pesa (Daraja)
- `FeeStructure(grade, term, year, amount)` → `Invoice(learner, term, year, amount_due)`.
- Parent pays via **STK Push** (school triggers from the portal) or **C2B paybill** with the learner's admission number as account reference.
- `payments/services/daraja.py` wraps OAuth token, STK Push, and callback validation; sandbox creds via env vars. Callbacks are idempotent — a replayed confirmation cannot double-credit an invoice.
- Reconciliation: every `MpesaTransaction` is matched to an invoice by account reference; unmatched ones queue for manual review.

### 2. Offline tolerance
- **Server side:** write endpoints for attendance and scores accept an `Idempotency-Key` header. A replayed request (same key) returns the stored first response instead of duplicating writes — safe queue-and-retry from flaky connections.
- **Client side:** the React app ships an `offlineQueue` fetch wrapper — failed writes are persisted to `localStorage` with a generated idempotency key and replayed automatically when connectivity returns (`online` event + interval flush).
- Bulk endpoints (`POST /api/attendance/bulk/`) so a whole class register syncs in one request.

### 3. KEMIS/NEMIS interoperability
- `GET /api/interop/kemis/learners.csv` — learner register in a KEMIS-shaped column layout (UPI, names, DOB, gender, grade, pathway).
- `GET /api/interop/kemis/enrollment/` — enrollment counts by grade/gender for returns.
- Exports are read-only views over live data; when KEMIS publishes a formal API, this app is the single integration point.

## API shape

`/api/` (DRF router): `schools/`, `learners/`, `pathways/`, `teachers/`, `assessments/`, `scores/`, `report-card/<learner>/`, `attendance/` (+ `bulk/`), `timetable/lessons/`, `communication/sms/`, `payments/invoices/`, `payments/stk-push/`, `payments/c2b-confirmation/` (webhook), `interop/kemis/…`.

Auth: session + token (DRF). Roles: `ADMIN`, `TEACHER`, `PARENT` on the custom `User` model (`apps/accounts`) — custom user model from day one, since it cannot be retrofitted.

## Phase 2 (built)

- **PDF report cards** — `assessments/reports.py` builds the report dict once for both the JSON API and `assessments/pdf.py` (reportlab). Batch generation per class is a Celery task writing to `MEDIA_ROOT/report_cards/`.
- **Parent portal (PWA)** — `Guardian.user` links a guardian to a `PARENT` login; `/api/parent/summary/` returns children + balances + report cards + announcements in one call. The React app switches to the parent UI based on `/api/me/`, and production builds install as a PWA (manifest + app-shell service worker; API traffic deliberately uncached — api.js owns offline write queueing).
- **Staff directory** — `Teacher` gained `employment_type` (TSC/PNP/BOM/PTA) and `rank` (Head → Intern); new `SupportStaff` model covers non-teaching roles (bursar, secretary, kitchen, cleaner, security, driver, nurse, librarian, grounds) with title, phone, and employment terms. `teachers/staff.py` serves the grouped directory (with teacher presence + subjects) and `SupportStaff` CRUD.
- **School structure** — `Learner.Grade` extended with PP1/PP2 (−1/0); `ClassGroup` assigns a class teacher per grade+stream; `TeacherAttendance` records staff presence. `schools/structure.py` serves the category tree (Primary/JSS/Senior) and per-grade detail (students + today's attendance, class-teacher panel with roll-call/schemes/subjects/timetable, class timetable); `LearnerViewSet.profile` aggregates scores, guardians, fees, and attendance per student (parents restricted to their own children).
- **Scheme-of-work workflow** — `SchemeOfWork` gained `document` (upload), `source` (MANUAL/UPLOADED/GENERATED), `status` (DRAFT/PENDING/APPROVED/REJECTED), and reviewer fields. Teachers upload or AI-generate (`teachers/services/ai_scheme.py`: Claude API `claude-opus-5` + structured-output JSON schema, stub template without credentials); both land PENDING. Admin-only `review` action records the decision, reviewer, and comment; the staff UI has a filterable review queue rendering the KICD-style weekly plan.
- **Teacher portal** — `/api/teacher/summary/` (personal timetable, markable assessments, schemes of work, announcements) plus `/api/scores/bulk/`, which mirrors bulk attendance: idempotency-keyed, upsert-converging, and validating marks against `max_marks` server-side. The React app routes `TEACHER` logins to their own tabbed UI (My Timetable, Score Entry, Attendance, Schemes of Work).
- **Timetable auto-generation** — `LessonRequirement` captures weekly needs; `timetable/generator.py` places lessons greedily (most-constrained first, day-spread, teacher/class/lab occupancy). Deliberately greedy for v1: deterministic, fast, and reports unplaced requirements instead of overbooking. Swap for CP-SAT (OR-Tools) later without touching the data model.
