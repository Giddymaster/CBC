# CBC School Management System (Kenya)

School management for the Competency-Based Curriculum: learners & pathways, CBC assessments (EE/ME/AE/BE), attendance, timetabling, SMS communication, **M-Pesa fee payments**, **offline-tolerant sync**, and **KEMIS/NEMIS exports**.

Stack: **Django + DRF + PostgreSQL/SQLite + Redis + Celery** (backend), **React + Vite** (frontend).

- [DESIGN.md](DESIGN.md) — architecture and the reasoning behind each decision
- [ROADMAP.md](ROADMAP.md) — what is built, what is missing, and the open gaps ranked

## Quick start

### Backend (Django)

```bash
cd backend
python -m venv ../backend-venv
../backend-venv/Scripts/pip install -r requirements.txt
../backend-venv/Scripts/python manage.py migrate
../backend-venv/Scripts/python manage.py seed_demo         # demo school + admin/admin login
../backend-venv/Scripts/python manage.py seed_curriculum   # illustrative curriculum documents
../backend-venv/Scripts/python manage.py runserver
```

- API: http://127.0.0.1:8000/api/ (token auth: `POST /api/auth/token/`)
- Admin: http://127.0.0.1:8000/admin/ (`admin` / `admin` after seeding — dev only)
- No `.env` needed for dev: SQLite database, SMS logged instead of sent, M-Pesa in stub mode, Celery tasks run inline. Copy `.env.example` to `.env` to configure real services (PostgreSQL, Africa's Talking, Daraja).

### Frontend (React + Vite)

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 (API requests proxy to the Django server). Sign in with `admin` / `admin` (staff UI), `mwalimu` / `mwalimu` (teacher portal), or `mzazi` / `mzazi` (parent portal). The production build is an installable PWA (manifest + offline app-shell service worker).

### Tests

```bash
cd backend
../backend-venv/Scripts/python manage.py test tests --settings=config.settings_test
```

363 tests, under four seconds. `config/settings_test.py` swaps in an in-memory database and
a fast password hasher — without it the suite takes minutes on real hashing.

Coverage is deliberately weighted toward the things that would be worst to get wrong:

- **Tenancy** (`tests/test_tenancy.py`) — two schools in one database; every read and write
  path is asserted to stop at the school border.
- **Supervision** (`tests/test_supervision.py`) — rank-based visibility, assigning work,
  messaging, report approval, and a cycle in the reporting line that must not hang.
- **Permissions** (`tests/test_permissions.py`) — admin-only writes, parents restricted to
  their own children, and self-promotion via the teacher endpoint.
- **Domain** (`tests/test_domain.py`) — competency derivation, bulk marks, attendance
  idempotency, M-Pesa double-credit protection, timetable clash rules, PG→G12 structure.
- **Schemes & facilities** (`tests/test_schemes_and_facilities.py`).
- **Knowledge base** (`tests/test_knowledge.py`) — chunking, BM25 retrieval, cross-tenant
  isolation of school documents, authority ordering, and the MoE canon including the
  pathway conflict.
- **Promotions** (`tests/test_promotions.py`) — preview, adjust, apply, reverse, and a
  whole-school round trip asserted to leave no trace.
- **Passwords and audit** (`tests/test_passwords_audit.py`) — token invalidation, forced
  change, and an append-only log that cannot be written or deleted through the API.
- **Deployment** (`tests/test_deployment.py`) — the production settings nobody runs
  locally: startup refusal without a real key, HSTS, secure cookies, Postgres selection.

Two older narrative scripts remain for manual walkthroughs:
`scripts/smoke_test.py` (payments, offline attendance) and `scripts/smoke_test2.py`
(PDF report cards, parent portal, timetable generation).

## PDF report cards, parent portal, timetable generation

- **PDF report cards:** `GET /api/report-card/<id>/pdf/?term=&year=` renders one learner on the fly (reportlab); `POST /api/report-cards/generate-class/` `{grade, stream, term, year}` runs a Celery task writing a PDF per learner to `media/report_cards/<year>/T<term>/`. The staff UI has a "Download PDF" button on the Report Card tab.
- **Parent portal:** guardians can be linked to a `PARENT` user (`Guardian.user`). `GET /api/me/` tells the frontend which UI to show; `GET /api/parent/summary/` returns the guardian's children with fee balances, current-year report cards, and parent-audience announcements in one call.
- **Staff directory (admin):** the **Staff** tab (`GET /api/school/staff/`) lists teaching staff grouped by employment category — Government (TSC), PNP, BOM, PTA — with each teacher's TSC/payroll number, rank (Head Teacher → Intern), subjects, and presence today, and non-teaching staff grouped by category (bursar, secretary, kitchen, cleaners, security, driver, nurse, librarian, grounds, other) with rank/title, phone, and employment terms. The tab's **Add staff** form covers both kinds: teaching staff (`POST /api/school/staff/add-teacher/`, admin-only — creates the portal user account plus the teacher profile with employment type and rank; username/password auto-generate if left blank, with the password shown once) and non-teaching staff (`/api/support-staff/` CRUD).
- **School structure (admin):** the staff UI's **School** tab shows the school in CBC categories — Primary (PP1, PP2, Grade 1–6), Junior School (Grade 7–9), Senior School (Grade 10–12) — with per-grade enrolment (total/male/female) and class teachers (`GET /api/school/structure/`). Opening a grade (`GET /api/school/grades/<grade>/`) shows the class teacher panel (present today, roll-call taken, subjects taught, schemes of work with review status, personal timetable), the student register (sortable by admission number/name, filterable by gender, with today's attendance status), and the class timetable with subject + teacher per slot. Each student links to a full profile (`GET /api/learners/<id>/profile/`): subject scores with competency levels, guardians with phone numbers, fee balance and invoices, and attendance history. Class teachers are assigned via `ClassGroup`; staff presence via `TeacherAttendance`. Parents cannot access the structure endpoints and can only open their own children's profiles.
- **Schemes of work — upload, AI generation, and head review:** teachers can upload a scheme document (`POST /api/schemes-of-work/` multipart with `document`) or have one AI-drafted (`POST /api/schemes-of-work/generate/` with learning area, grade, term, weeks). Either path lands the scheme in **Pending review**; the admin/head sees a "Schemes Review" queue in the staff UI where they open the uploaded file or the structured weekly plan and approve/reject with a comment (`POST /api/schemes-of-work/<id>/review/`, admin-only). Generation uses the Claude API (`claude-opus-5` with a JSON-schema-constrained response) when `ANTHROPIC_API_KEY` is set in `backend/.env`; without a key it falls back to a deterministic KICD-style template so the workflow works offline.
- **Teacher portal:** `TEACHER` logins get their own UI. `GET /api/teacher/summary/` returns the teacher's personal timetable, the assessments they can mark (derived from their lesson requirements/lessons; stream-blank assessments cover the whole grade), their schemes of work, and teacher-audience announcements. `POST /api/scores/bulk/` enters a whole class's marks in one offline-tolerant request (Idempotency-Key replay-safe, upserted on assessment+learner, invalid rows skipped and reported) and returns the derived EE/ME/AE/BE level per learner. Portal tabs: My Timetable, Score Entry, Attendance, Schemes of Work.
- **Timetable generation:** define weekly needs in `/api/timetable/requirements/` (teacher, learning area, class, lessons/week, needs_lab), then `POST /api/timetable/generate/` places lessons greedily — most-constrained first, spread across days, honoring teacher/class/lab availability — and reports anything it could not place. The Timetable tab shows the grid with a regenerate button.

## Curriculum knowledge base (RAG)

Generated schemes of work are **retrieval-augmented**: before drafting, the relevant
passages are pulled from the school's curriculum library and passed as context, and the
model is required to work from them and cite them by number.

- **Library** (`/api/curriculum/documents/`) — KICD curriculum designs, MoE circulars,
  approved course books, teacher guides, question banks. Documents are chunked on their
  own headings, so a citation reads *"Grade 7 Integrated Science — Sub-strand 2.1
  Mixtures"* rather than "page 4".
- **Retrieval** is lexical BM25 — no API key, no vector database, no network. That matters
  for a school on intermittent connectivity. Search: `/api/curriculum/search/?q=`.
- **National vs school documents:** a document with no school is national and readable by
  every tenant; only a platform superuser can publish one. A school admin adds their own
  school's documents, which never leave that tenant.
- **Provenance:** every generated scheme carries a `grounding` block — how many passages,
  which sources with full citations, and the governing authority. If the library has
  nothing for that subject and grade, the scheme says so plainly so the head teacher
  reviewing it knows it was written without the curriculum design.

### Conflict rule: MoE governs

`apps/schools/moe.py` is the single definition of Kenyan basic-education structure —
levels, pathways, competency levels, transitions — and the authority precedence:

**MoE › KICD › KNEC › TSC › County › School › Other**

Retrieval weights passages by that order and reports when sources of differing standing
both matched, naming the one that governs. The generator is told the precedence explicitly.
Two conflicts already resolved this way are recorded in that module:

- The founding brief named **four** Senior School pathways. MoE defines **three** —
  "Humanities" is a *track* inside Social Sciences, not a pathway. `pathway_for_track()`
  resolves the brief's term to the MoE structure, so the intent survives and the structure
  follows MoE.
- The brief's "Primary / JSS / Senior" is replaced by the fuller MoE breakdown
  (Pre-Primary, Lower Primary, Upper Primary, Junior School, Senior School).

`GET /api/moe/structure/` publishes the canon; the Curriculum Library page shows it.

## Admissions

- **The form** (`POST /api/admissions/`) takes the whole admission in one transaction —
  the child, up to four guardians, and the emergency contact. It captures identity
  (birth certificate, UPI, nationality, religion), home (county/sub-county/ward, address,
  day or boarder, how they travel and on which bus route), **health** (blood group,
  allergies, chronic conditions, regular medication, NHIF, immunisation, special needs),
  next of kin, and the previous school. Only name, date of birth and grade are required —
  a family arriving without paperwork should not be a reason a child cannot be enrolled.
- **Admission numbers** continue the school's own sequence: `ADM0281 → ADM0282`. Leave the
  field blank and the next number is assigned; supply one and a duplicate is rejected.
- **Siblings** reuse the existing guardian record rather than creating a second copy of the
  same parent.
- **Profile photos:** `POST /api/learners/<id>/photo/` (multipart). Photos show on the
  learner register, the class register and the student profile; initials stand in until one
  is uploaded.
- **Delegation:** admitting is an admin power by default. From **Staff → Admission rights**
  the admin grants it to a named staff member — head teacher, deputy, or the class teacher
  running the Grade 1 intake — with a note and an optional expiry date. The delegate then
  gets an **Admissions** tab in their own portal, without any other admin access. Rights can
  be withdrawn or restored, and the record of who granted what is kept.
- **Privacy:** medical detail, home address and next-of-kin data are staff-only. Parents
  reading the learner API never receive them, and they are not part of the KEMIS export.

## Notifications

The bell in the topbar (`GET /api/notifications/`) is on every staff login. It shows four
things that arrive unannounced: a **message from a supervisor**, **work assigned** to you
(flagged when overdue), a **report awaiting your approval**, and a **report of yours
returned** for changes. Messages can be marked read; tasks and pending reviews stay listed
until the work itself is done, which is the honest signal.

## Facilities and staff portals

- **Facilities (admin):** the sidebar is school-definable — **sections** (Academics, Facilities,
  Finance…) hold **categories** (Transport, Dormitories, Infirmary, Libraries, Laboratories,
  Kitchen…), which hold individual facilities. Each facility page lists the staff posted there
  with their positions, and its supplies with a derived in-stock / low / depleted status.
  Admins add sections and categories from the sidebar itself (`/api/nav-sections/`,
  `/api/facility-categories/`).
- **Staff portals:** every staff login — teaching or not — gets `GET /api/my-portal/`: their
  profile with photo, their department and rank, what they are responsible for (classes,
  lessons, facilities, duties), **who their supervisor is**, work assigned to them, and their
  reports. Reports flow `DRAFT → SUBMITTED → APPROVED / RETURNED` up the reporting line.
- **Supervisor view:** anyone who supervises someone gets a **My Team** tab
  (`/api/my-team/`) listing their staff **grouped by category**, with open work and reports
  pending per person. Opening a person (`/api/my-team/<user_id>/`) gives their profile and
  responsibilities, a form to **assign work**, **their reports** with inline approve/return,
  and a private **message thread**.
- **Rank decides reach:** Head/Deputy see the whole school; a Senior Teacher — or any
  non-teaching staff member who supervises someone — sees their own reporting subtree;
  everyone else sees only direct reports. The school border always holds, whatever the rank.
  Supervisors are assigned from the Staff page's edit form.

## The three flagship integrations

- **M-Pesa (Daraja):** `POST /api/payments/stk-push/` triggers an STK push for an invoice; `stk-callback/` and `c2b-confirmation/` webhooks credit invoices idempotently (unique M-Pesa receipt — replays can't double-credit). C2B payments match learners by admission number (`BillRefNumber`).
- **Offline tolerance:** write endpoints honor an `Idempotency-Key` header (replay returns the stored response). The frontend queues failed writes in `localStorage` and replays them on reconnect. `POST /api/attendance/bulk/` upserts a whole class register in one retryable request.
- **KEMIS/NEMIS:** `GET /api/interop/kemis/learners.csv` (learner register) and `GET /api/interop/kemis/enrollment/` (counts by grade/gender).

## Project layout

```
backend/
  config/          settings, urls, celery
  apps/
    common/        multi-tenancy base models, idempotency store, seed_demo
    accounts/      custom User (roles: ADMIN/TEACHER/PARENT)
    schools/       School (tenant root)
    students/      Learner, Pathway, Guardian
    teachers/      Teacher, SchemeOfWork, LessonPlan, PD records
    assessments/   LearningArea, Assessment, Score (auto EE/ME/AE/BE), report card
    attendance/    AttendanceRecord + offline bulk sync
    timetable/     Room, Period, Lesson (clash detection)
    communication/ SMS (Africa's Talking), announcements, Celery blasts
    payments/      FeeStructure, Invoice, M-Pesa Daraja + reconciliation
    interop/       KEMIS/NEMIS exports
    facilities/    NavSection, FacilityCategory, Facility, assignments, supplies
    knowledge/     curriculum library: Source (authority), Document, Chunk, BM25 retrieval
  tests/           test suite (tenancy, supervision, permissions, domain)
frontend/          React + Vite: login, learners, offline attendance register,
                   report cards, fees + STK push; offline queue in src/api.js
```

## Accounts and passwords

- A staff member changes their own password at any time (`POST /api/me/password/`), which
  **invalidates the existing token** — a password change is usually a response to it being
  known by someone else, and leaving old tokens alive would make it cosmetic. A fresh token
  comes back so the current session continues.
- The admin resets a forgotten one (`POST /api/school/staff/<user_id>/reset-password/`). The
  new password is shown once and the account is flagged: **the app is unreachable until the
  holder replaces it**. That is what stops the admin's copy remaining a working credential.
- The same flag is set on any password the system generates when creating a staff account.

## Audit trail

`GET /api/audit/` records the decisions a school would be asked about later — a mark
corrected (with both values and both competency levels), a learner admitted or deactivated,
a report or scheme reviewed, a promotion applied or reversed, rights granted, a password
reset, a payment received.

Deliberately explicit rather than signal-driven: a `post_save` hook on every model would log
migrations and seed data, and the useful entries would drown. **Append-only** — there is no
create, update or delete endpoint, because a log an admin can edit is not evidence of
anything. An audit write can never fail the action it describes.

## Running the production stack locally

The dev default needs none of this — SQLite, eager Celery, no Redis. Use compose when you
want the engine production actually uses:

```bash
docker compose up --build
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py seed_demo
```

CI (`.github/workflows/ci.yml`) runs the suite twice — once on SQLite, once on **PostgreSQL
16** — plus `manage.py check --deploy` with `DEBUG=false`, a check that the app refuses to
start without a real `SECRET_KEY`, a missing-migration check, and the frontend build.

## Production notes

- Set `POSTGRES_DB` etc. to switch to PostgreSQL; set `DEBUG=false` (Celery then requires a real Redis at `REDIS_URL`).
- With `DEBUG=false` the app **refuses to start** without a real `SECRET_KEY`, and turns on HSTS, secure cookies, SSL redirect and `X-Frame-Options: DENY`. Set `CORS_ALLOWED_ORIGINS` to your real frontend origin.
- Registers of learner data fall under the Kenya Data Protection Act 2019 — register as a data controller before going live. The KEMIS exports are admin-only for this reason.
- Daraja callbacks must be HTTPS-reachable (`DARAJA_CALLBACK_URL`); register the C2B confirmation URL on the paybill.
- **The app has never been run against the real Daraja sandbox.** Do that before go-live — see [ROADMAP.md](ROADMAP.md) for the full pre-deployment gap list. PostgreSQL is now covered by CI.
