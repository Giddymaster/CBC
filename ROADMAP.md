# Roadmap & Delivery Tracker

Tracks every commitment made in the original design brief ([DESIGN.md](DESIGN.md)) plus the
features requested since, against what is actually built and tested.

**Legend:** ✅ built & tested · 🟡 built, gaps noted · ⬜ not started · ➖ deliberately deferred

Last reviewed: **2026-08-05** · Backend suite: **111 tests, all passing**
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

| # | Module | Status | Evidence / gap |
|---|---|---|---|
| 1 | Student Information System | ✅ | Learner (UPI, admission no), pathways, guardians, PG→G12 grades, custom columns. |
| 2 | Teacher Management | ✅ | TSC/payroll no, employment type, rank, subjects, schemes, PD records. |
| 3 | Assessment Engine | ✅ | CAT1/CAT2/End-term/formative, auto EE/ME/AE/BE, per-assessment rubric override, report cards. |
| 4 | Timetable | ✅ | Clash detection at write time + greedy auto-generation with unplaced reporting. |
| 5 | Communication Hub | 🟡 | SMS + announcements + meeting links. WhatsApp deferred. |
| 6 | Attendance Register | ✅ | Learner + teacher roll-call, offline-tolerant bulk sync. |
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
