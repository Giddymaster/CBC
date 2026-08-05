# Roadmap & Delivery Tracker

Tracks every commitment made in the original design brief ([DESIGN.md](DESIGN.md)) plus the
features requested since, against what is actually built and tested.

**Legend:** ✅ built & tested · 🟡 built, gaps noted · ⬜ not started · ➖ deliberately deferred

Last reviewed: **2026-08-05** · Backend suite: **160 tests, all passing**
(`python manage.py test tests --settings=config.settings_test`)

---

## 1. Tech stack commitments

| Layer | Committed | Status | Notes |
|---|---|---|---|
| Backend | Django + DRF + PostgreSQL + Redis + Celery | 🟡 | All code present. PostgreSQL is env-switched but **never run against**; Celery runs eager in dev — neither is exercised in CI. |
| Frontend | React (web) + PWA parent portal | ✅ | Vite build, manifest + app-shell service worker. |
| Payments | M-Pesa Daraja — STK Push + C2B | 🟡 | Full flow + idempotent reconciliation, tested. **Never run against the real sandbox** — stub mode only. |
| Communication | Africa's Talking SMS, meeting deep-links | 🟡 | SMS service + stub. **WhatsApp Business API not started.** |
| Analytics | Metabase on PostgreSQL | ⬜ | Nothing yet. Needs Postgres first. |
| Security | Django auth; allauth/Google Workspace; Cloudflare Zero Trust | 🟡 | Token + session auth done. **No allauth, no SSO, no Zero Trust.** |
| Infrastructure | AWS af-south-1 + Cloudflare | ⬜ | No deployment, no IaC, no CI. |

## 2. Core modules

Graded against the **DESIGN.md** module list, which is narrower than the founding brief.
**§8 below grades the same modules against the original brief and is the stricter, truer
scorecard** — several rows here read ✅ only because DESIGN.md asked for less.

| # | Module | Status | Evidence / gap |
|---|---|---|---|
| 1 | Student Information System | 🟡 | Learner (UPI, admission no), guardians, PG→G12, custom columns ✅. Pathway is stored but **assigned by hand** — see §8.1. |
| 2 | Teacher Management | 🟡 | TSC/payroll no, employment type, rank, subjects, schemes ✅. **PD records are a model only — no API, no UI. Lesson plans have no UI.** |
| 3 | Assessment Engine | ✅ | CAT1/CAT2/End-term/formative, auto EE/ME/AE/BE, per-assessment rubric override, report cards. |
| 4 | Timetable | ✅ | Clash detection at write time + greedy auto-generation with unplaced reporting. |
| 5 | Communication Hub | 🟡 | SMS + announcements + meeting links + staff notifications. **No parent↔teacher messaging.** WhatsApp deferred. |
| 6 | Attendance Register | 🟡 | Learner roll-call ✅ offline-tolerant. **Teacher roll-call has no UI and nothing writes to it but seeds.** |
| 7 | Payments / Fees | ✅ | Fee structures, invoices, STK Push, C2B webhook, receipt-idempotent reconciliation. |
| 8 | Interoperability | ✅ | KEMIS learner CSV + enrollment returns, admin-only. |

## 3. The three flagship integrations

| Item | Status | Notes |
|---|---|---|
| M-Pesa payments | 🟡 | Logic complete and tested; a replayed callback provably cannot double-credit. Sandbox credentials never exercised. |
| Offline tolerance | ✅ | `Idempotency-Key` replay on the server, localStorage queue on the client, and rejected replays now surface to the user instead of vanishing. |
| KEMIS/NEMIS interop | ✅ | Read-only exports over live data; single integration point when MoE ships an API. |

## 4. Delivered since the brief

| Feature | Status |
|---|---|
| PDF report cards (single + Celery batch per class) | ✅ |
| Parent PWA portal (children, balances, report cards, announcements) | ✅ |
| Timetable auto-generation | ✅ |
| Teacher portal (timetable, score entry, attendance, schemes) | ✅ |
| Scheme of work: upload, AI generation, head review queue | ✅ |
| Admin school structure: categories → grade → student profile | ✅ |
| Staff directory: teaching (TSC/PNP/BOM/PTA + ranks) and non-teaching by category | ✅ |
| Excel-style custom columns on learners and staff | ✅ |
| Edit / deactivate learners and staff | ✅ |
| Facilities: sections → categories → facility, with staff posts and supplies | ✅ |
| Admin-definable sidebar sections and categories | ✅ |
| Staff portals: my role, responsibilities, supervisor, report submission & approval | ✅ |
| Supervisor team view: staff by category, assign work, review reports, message thread | ✅ |
| Rank-based visibility (head → whole school, section head → subtree, staff → direct) | ✅ |
| Play Group (PG) grade | ✅ |
| Full admission form (identity, home, health, next of kin, previous school) | ✅ |
| Learner profile photos on register, class list and profile | ✅ |
| Delegated admission rights (admin → head teacher / class teacher, with expiry) | ✅ |
| Notification bell: supervisor messages, assigned work, reviews, returned reports | ✅ |
| Curriculum knowledge base (RAG): documents → chunks → BM25 retrieval with citations | ✅ |
| MoE canon as the single authority, with source precedence for conflicts | ✅ |
| Grounded scheme generation with provenance shown to the reviewer | ✅ |

---

## 5. Open gaps — ranked

### Blocking a real deployment
1. **No CI and no deployment pipeline.** The suite exists but nothing runs it automatically. ⬜
2. **Never run on PostgreSQL.** SQLite hides case-sensitivity, transaction and constraint
   differences. At minimum, run the suite against Postgres once before go-live. ⬜
3. ~~Production settings are unguarded~~ — **done**: with `DEBUG=false` the app refuses to
   start without a real `SECRET_KEY`, and enables HSTS, secure cookies, SSL redirect and
   `X-Frame-Options: DENY`. Still never deployed, so still unproven in practice. ✅
4. **Kenya DPA 2019 registration** as a data controller — a legal precondition, not a code
   task. Now more pressing: the admission form holds medical records on minors. ⬜

### Correctness / safety
5. **No audit trail.** Who changed a mark, deactivated a learner, or approved a report is not
   recorded beyond `updated_at`. For a system holding minors' records this is the largest
   remaining integrity gap. ⬜
6. **`IdempotentRequest` grows without bound** — needs a TTL prune job. ⬜
7. **Bulk endpoints are not rate-limited.** ⬜

### Product gaps a school would hit in term one
8. ~~Supervisor cannot be set from the admin UI~~ — **done**: dropdown on both staff forms,
   Supervisor column on both tables, self-supervision rejected server-side. ✅
9. **No password reset / change-password flow.** Admin-generated passwords are shown once and
   cannot be rotated by the staff member. ⬜
10. **No promotion / end-of-year rollover** — moving a whole grade up a year. ⬜
11. **No transfer-out or alumni state** — a learner can only be deactivated. ⬜
12. **No fee statement or receipt PDF** for parents. ⬜
13. **No exam analytics** (class mean, subject ranking, term-on-term movement). ⬜
14. **No bulk learner import** (CSV) — learners are admitted one at a time through the
    admission form; a January intake of 200 would want a spreadsheet upload. ⬜
15. **Teacher attendance has no UI** — the model and API exist; nothing writes to it except seeds. 🟡

### Deferred on purpose
- Flutter native apps — the PWA covers the parent case. ➖
- OR-Tools CP-SAT timetabling — the greedy generator is deterministic and reports failures. ➖
- Schema-per-tenant — row scoping is enforced and tested; migrate only if a mega-tenant demands it. ➖
- ML/predictive analytics — needs 2–3 terms of real data first. ➖

---

## 6. Bugs found and fixed in the 2026-08-05 audit

Each of these was found by writing the test first; all are now covered by regression tests.

| # | Severity | Bug | Fix |
|---|---|---|---|
| 1 | **High** | Any teacher could `PATCH /api/teachers/<id>/` to set their own rank to `HEAD`, which grants whole-school visibility — a self-service promotion. | `TeacherViewSet` writes are now admin-only. |
| 2 | **High** | KEMIS exports had no role check: any authenticated login, including a parent, could download every learner's name, UPI and date of birth. | Admin-only, with the DPA rationale recorded in the code. |
| 3 | **High** | An admin could open, message and read staff belonging to **another school** via `/api/my-team/<id>/` — the admin bypass skipped the tenancy filter. | Removed the bypass; `visible_staff_ids` grants whole-school reach *and* enforces the school border. |
| 4 | **High** | Correcting a mark saved the new score but kept the competency level derived from the **old** mark — wrong grades on report cards. `update_or_create` passes `update_fields`, which excluded the recomputed field. | `Score.save()` now always includes `competency_level` in `update_fields`. |
| 5 | Medium | Teachers could read every colleague's schemes of work, and re-submit someone else's rejected scheme. | Queryset scoped to own + supervised staff; `submit` restricted to the owner. |
| 6 | Medium | A task assignee could PATCH `assigned_to` and `title` — reassigning their own work to someone else. | Assignees may change status only. |
| 7 | Medium | Paginated lists had no default ordering, so page 2 could repeat or skip rows. Django was warning about it on every request. | Default `ordering` on all 25 paginated models. |
| 8 | Medium | Two idempotent retries racing produced an `IntegrityError` 500, and stored 4xx/5xx responses made transient failures permanent for that key. | Race is caught and replays the winner; only 2xx responses are stored. |
| 9 | Medium | Offline writes rejected with a 4xx were dropped silently — a teacher's register could never land and nobody would know. | Rejections are kept and shown in a banner until dismissed. |
| 10 | Low | `/api/staff-messages/?with=abc` returned a 500. | Validated, returns 400. |
| 11 | Low | Unauthenticated API calls returned 403, so the client could not tell "logged out" from "not allowed"; an expired token left every panel broken. | Token auth first (401), and the client now drops to the login screen. |
| 12 | Low | Parent portal children had no `id`/`name` at the top level. | Added, so the PWA can key and link on them. |
| 13 | Low | `MyTeamView` ran ~5 queries per staff member. | Grouped counts + `select_related` on both profile types. |

## 7. Admissions, photos, delegation and notifications (2026-08-05)

31 further tests, all passing. Two things worth recording:

- The dev server had been started with `--noreload`, so new URL routes 404'd until it was
  restarted. Worth knowing before diagnosing a "missing endpoint".
- The notification panel inherited the topbar's `text-transform: uppercase`, which SHOUTED
  every message body. Reset on the panel.

Still open in this area:

- **No CSV bulk import** for a whole intake (see gap 14).
- **Photos are not resized or size-limited on upload** — a 12 MP phone photo is stored as-is.
  Worth a Pillow downscale before a school with 300 learners fills the disk. ⬜
- **No sibling linkage** beyond the shared guardian record — the form reuses the parent, but
  there is no "these two learners are siblings" view. ⬜

---

## 8. The original brief, section by section

The six-part brief, audited against the code on 2026-08-05. This is the master
scorecard; sections 1–7 above track how we got here.

**Roughly 55% delivered.** The split is not even: the *administrative spine* is
essentially done, and the *teaching-and-learning half* is barely started.

### 1. Core Modules — 3 complete, 3 partial, 1 absent

| Module | Status | Reality |
|---|---|---|
| Student Information System | 🟡 | Learner profiles ✅ (full admission record), competency tracking EE/ME/AE/BE ✅. **Pathway assignment is a manual dropdown — no automation, no Grade 9→10 rule.** |
| Teacher Management | 🟡 | Schemes of work ✅. **Lesson plans: model + API, zero UI. Teacher attendance: model + API, no UI, nothing writes to it but seeds. Performance analysis: nothing. PD records: model only — not even exposed over REST.** |
| Assessment Engine | ✅ | CAT1/CAT2/End-term/formative, CBC rubrics with per-assessment override, automated report cards (JSON + PDF + Celery batch). The most complete module. |
| Timetable Generator | ✅ | Auto-scheduling across teachers, rooms and labs with clash avoidance and unplaced reporting. Delivered as specified. |
| Communication Hub | 🟡 | SMS ✅, announcements ✅, staff notifications ✅. **No parent↔teacher messaging at all. No parent notifications. Teams/Zoom is a deep link on an announcement, not an interface.** |
| Attendance Register | 🟡 | Learner roll-call ✅ offline-tolerant. Teacher roll-call has no UI. **Biometric: not started.** |
| Smart Board Integration | ⬜ | Nothing. No interactive lessons, no multimedia, no annotation. |

### 2. Resources & Books — 0 of 4

Nothing exists. No model, no endpoint, no screen.

| Item | Status |
|---|---|
| MoE-approved CBC textbooks (Grade 7–12) | 🟡 |
| Digital libraries (Kenya Education Cloud, KICD e-books) | 🟡 |
| Teacher guides (scheme/lesson-plan templates) | 🟡 |
| Assessment banks (CBC-aligned question pools) | 🟡 |

**Updated 2026-08-05.** The **curriculum knowledge base** now provides the store: a
school uploads designs, circulars, course books, guides and question banks; they are
chunked, indexed and retrievable with citations, and they ground generated schemes.

What is still missing is the *content itself* and the reader:

- No actual KICD designs are bundled — a school must obtain and upload them. The seed
  command loads short illustrative extracts, clearly labelled as demo.
- No Kenya Education Cloud / KICD e-book integration; ingestion is manual upload.
- Question banks can be stored and searched but there is no item model, no paper
  assembly and no delivery to learners.
- PDF text extraction needs `pypdf`; without it a PDF stores but does not index.

### 3. Communication & Collaboration — 1 of 3

| Item | Status | Reality |
|---|---|---|
| Teams/Zoom for remote classes | ⬜ | A `meeting_link` URL field on announcements. Deliberate ("deep-links, not embedded SDKs") but it is not the integration the brief asked for. |
| Parent portal | ✅ | Progress reports, fee balances and announcements — all three named items, as an installable PWA. |
| Admin dashboards for boards + MoE compliance | 🟡 | KEMIS learner register and enrollment returns export cleanly. There is no dashboard, and nothing built for a school board. |

### 4. Teacher Analysis & Support — the weakest section, ~0.5 of 3

| Item | Status | Reality |
|---|---|---|
| Performance dashboards (learner outcomes per teacher) | ⬜ | No aggregate query exists anywhere in the codebase. |
| PD logs linked to TSC training records | ⬜ | `ProfessionalDevelopmentRecord` exists as a model and is reachable only through Django admin. No API, no UI, no TSC link. |
| Feedback loops — peer review of schemes and lesson plans | 🟡 | Head/admin review of schemes ✅. **Peer** review does not exist, and lesson plans are not reviewable at all. |

### 5. MoE Compliance — ~0.5 of 3

| Item | Status | Reality |
|---|---|---|
| Governance (JSS BoM, Parents Association) | 🟡 | BOM/PTA exist as staff *employment types*. The governance bodies themselves are not modelled: no BoM member register, no terms of office, no meeting records. |
| CBC pathways: automated assignment and grading | 🟡 | Grading ✅. **Assignment is manual.** |
| Transition rules 6→7, 9→10, 12→tertiary | ⬜ | Nothing. There is no promotion or end-of-year rollover of any kind. |

### 6. Software inspirations

| Inspiration | How we compare |
|---|---|
| Edupath SMS | Continuous assessment ✅ and report cards ✅ match. Automated pathway assignment does not. |
| KEMIS | Closest match — national data exports ✅, resource tracking ✅ (facilities, staff posts, supplies), teacher attendance partial. |
| Moodle / Google Classroom | **No overlap.** No content delivery, no assignments, no submissions, no learner-facing surface at all. Learners have no login. |

---

## 9. What we have actually been building

Every feature added since the brief — facilities, staff portals, supervision,
admissions, notifications — deepened **school administration**. None of it
touched **teaching and learning**.

The system today runs a school's office very well: who is enrolled, who works
here, who reports to whom, who paid, who is present, what the timetable is.

It does not yet serve a lesson. There is no learner login, no content, no
assignment, no submission, and no way to tell a head teacher which classes are
falling behind.

## 10. Recommended order from here

1. **Transitions and end-of-year rollover** (brief §5) — *the blocker*. Without
   promotion, the system cannot survive into a second academic year: Grade 6
   never becomes Grade 7. Bundle the Grade 9→10 **automated pathway assignment**
   into the same work, since that is the transition that needs it. Also unlocks
   alumni/transfer-out state (gap 11).
2. **Teacher analysis** (brief §4) — an entire numbered section at zero. Class
   mean per teacher, competency distribution, term-on-term movement, PD records
   over the API, peer review of schemes. Mostly aggregate queries over data we
   already hold, so the cost is low relative to the value.
3. **Parent↔teacher messaging and parent notifications** — closes the
   Communication Hub. The `StaffMessage` and notification machinery already
   exists; it needs a parent-facing channel.
4. **Resources and question banks** (brief §2) — the *store* now exists (see §11).
   What remains is real content, an ingestion path better than manual upload, and a
   question-item model that can assemble a paper.
5. **Learner-facing surface** — the Moodle/Classroom half. The largest piece and
   the right one to do last, since it depends on 1, 2 and 4.

Cheap items worth folding in along the way: lesson-plan UI, teacher-attendance
UI, CSV bulk import, photo downscaling on upload.


---

## 11. Curriculum RAG and the MoE conflict rule (2026-08-05)

Built on request: retrieval-augmented generation grounded in authoritative documents,
with MoE structure governing conflicts.

**`apps/schools/moe.py`** is now the single definition of Kenyan basic-education
structure — levels, the three Senior School pathways and their tracks, competency
levels, transition points — and of source precedence:

`MOE › KICD › KNEC › TSC › COUNTY › SCHOOL › OTHER`

Conflicts resolved and recorded in that module:

| Conflict | Resolution |
|---|---|
| Brief named **four** pathways (incl. Humanities) | MoE defines **three**. Humanities is a *track* inside Social Sciences. `pathway_for_track("Humanities")` → `SOCIAL`, so the brief's intent survives under the MoE structure. |
| Brief's "Primary / JSS / Senior" | Replaced by the fuller MoE breakdown: Pre-Primary, Lower Primary, Upper Primary, Junior School, Senior School. |

**`apps/knowledge/`** holds the library: `Source` (carries the authority),
`Document` (national when `school` is null, otherwise tenant-private), `Chunk`.
Retrieval is lexical BM25 with authority weighting — no API key, no vector database,
no network, because a school on intermittent connectivity still needs it to work.
Documents chunk on their own headings so citations name the sub-strand.

Scheme generation now retrieves before drafting, passes cited context, states the
precedence to the model, and attaches a `grounding` block the reviewer can read: how
many passages, from which sources, and which authority governs. With an empty library
it says so rather than pretending.

### Bug found by these tests

**Negative IDF silently emptied results.** Document frequency was accumulated over the
query's term *list* rather than its distinct terms, so a query repeating a word
("strand sub-strand") counted that word twice per chunk. With `n` above the corpus size,
`log(1 + (total − n + 0.5)/(n + 0.5))` went negative, dragged the passage score below
zero, and the `score <= 0` guard discarded everything. Fixed by iterating distinct terms
and flooring IDF at zero; both are covered by regression tests.

Also fixed while here: chunk **headings were not indexed**, so "Sub-strand 2.1 Mixtures"
— exactly what a teacher searches for — was unfindable. Headings now index with the body.

### Still open in this area

- **Retrieval is lexical, not semantic.** "How do learners separate salt from sand?"
  will not match a passage phrased differently. An embedding backend is stubbed for but
  not implemented. ⬜
- **No re-ranking.** Top-k goes straight to the prompt. ⬜
- **Authority weighting is a heuristic, not contradiction detection.** It reports that
  sources of differing standing matched and names the governing one; it does not read
  them and decide they disagree. Named honestly in the code and the UI. ⬜
- **No document versioning** — re-uploading a design replaces it, losing what a scheme
  approved last term was grounded in. Worth having before an audit trail matters. ⬜
