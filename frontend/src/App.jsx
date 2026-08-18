import { useCallback, useEffect, useState } from 'react'
import {
  apiGet,
  apiWrite,
  clearRejectedWrites,
  clearToken,
  discardQueue,
  flushQueue,
  getToken,
  queuedCount,
  queuedWrites,
  rejectedWrites,
  setToken,
  setUnauthorizedHandler,
  startQueueFlusher,
} from './api.js'
import Admission from './Admission.jsx'
import Analysis from './Analysis.jsx'
import Broadsheet from './Broadsheet.jsx'
import TaskHub from './TaskHub.jsx'
import Audit from './Audit.jsx'
import Attendance from './Attendance.jsx'
import Curriculum from './Curriculum.jsx'
import { AddColumnHeader, ColumnHeader, columnApi } from './columns.jsx'
import Facilities, { ADD_CATEGORY } from './Facilities.jsx'
import Fees from './Fees.jsx'
import Learning from './Learning.jsx'
import Messaging from './Messaging.jsx'
import { basePathFor, goTo, portalFor, slugify, usePath } from './router.js'
import SchoolProfile from './SchoolProfile.jsx'
import { ALL_GRADES, gradeLabel, gradeParam } from './format.js'
import Notifications from './Notifications.jsx'
import ParentPortal from './ParentPortal.jsx'
import { ForcedPasswordChange, PasswordInput } from './Password.jsx'
import { ForgotPassword, ResetByLink } from './PasswordReset.jsx'
import Operator from './Operator.jsx'
import Subscription, { PlatformAnnouncements } from './Subscription.jsx'
import Promotions from './Promotions.jsx'
import SchemesReview from './SchemesReview.jsx'
import StaffRollCall from './StaffRollCall.jsx'
import SchoolStructure, { LearnerPhoto } from './SchoolStructure.jsx'
import Staff from './Staff.jsx'
import SupportPortal from './StaffPortal.jsx'
import TeacherPortal from './TeacherPortal.jsx'
import Timetable from './Timetable.jsx'

// The landing page links here as /login?as=parent|staff|admin. The role was
// chosen there, so this page carries no role switcher and no explainer — just
// the fields, labelled for who is signing in. Everyone authenticates through
// the same endpoint and the app routes each account to its own portal after.
// The school code is required for every school-bound login; only the operator
// (its own door at /operator/login, off the public menu) has none, because an
// operator belongs to no single school.
const LOGIN_ROLES = {
  parent: {
    heading: 'Parent sign-in',
    userLabel: "Child's admission number",
    passLabel: 'UPI number',
  },
  staff: {
    heading: 'Staff sign-in',
    userLabel: 'Username',
    passLabel: 'Password',
  },
  admin: {
    heading: 'Administrator sign-in',
    userLabel: 'Username',
    passLabel: 'Password',
  },
  operator: {
    heading: 'Operator sign-in',
    userLabel: 'Username',
    passLabel: 'Password',
    hideCode: true,
  },
}

function Login({ onLogin }) {
  const [forgot, setForgot] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  // 2FA: null until the server asks; then {channel, target} while we wait for
  // the one-time code.
  const [challenge, setChallenge] = useState(null)
  const [code, setCode] = useState('')
  const [schoolCode, setSchoolCode] = useState(
    () => new URLSearchParams(window.location.search).get('school') || '',
  )
  const [error, setError] = useState('')
  // The operator has its own door at /operator/login; everyone else picks a
  // role with ?as=. Reading the operator role from the path keeps it out of the
  // public ?as= menu.
  const asRole = window.location.pathname === '/operator/login'
    ? 'operator'
    : new URLSearchParams(window.location.search).get('as')
  const role = LOGIN_ROLES[asRole] || {
    heading: 'Sign in',
    userLabel: 'Username or admission number',
    passLabel: 'Password',
  }

  async function submit(e) {
    e.preventDefault()
    setError('')
    if (!role.hideCode && !schoolCode.trim()) {
      setError('Enter your school code — the office can tell you it.')
      return
    }
    try {
      const res = await fetch('/api/auth/token/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username, password, school_code: schoolCode.trim(),
          ...(challenge && code ? { code: code.trim() } : {}),
        }),
      })
      if (!res.ok) throw new Error(challenge ? 'That code is wrong or has expired' : 'Invalid credentials')
      const data = await res.json()
      // Right password + 2FA on → the server sent a code and wants it back.
      if (data.two_factor_required) {
        setChallenge({ channel: data.channel, target: data.target })
        setCode('')
        return
      }
      setToken(data.token)
      onLogin()
    } catch (err) {
      setError(err.message)
    }
  }

  if (forgot) return <ForgotPassword onBack={() => setForgot(false)} />

  if (challenge) {
    return (
      <form className="login" onSubmit={submit}>
        <img src="/logo.svg" alt="ShuleNest" className="login-logo" />
        <h2>Enter your sign-in code</h2>
        <p className="muted">
          We sent a 6-digit code to {challenge.target}
          {challenge.channel === 'SMS' ? ' by SMS' : ' by email'}.
        </p>
        <input placeholder="6-digit code" value={code} inputMode="numeric"
          maxLength={6} autoFocus
          onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} />
        <button className="primary" type="submit" disabled={code.length !== 6}>
          Verify and sign in
        </button>
        <button type="button" className="linkish"
          onClick={() => { setChallenge(null); setCode(''); setError('') }}>
          Back
        </button>
        {error && <div className="error">{error}</div>}
      </form>
    )
  }

  return (
    <form className="login" onSubmit={submit}>
      <img src="/logo.svg" alt="ShuleNest" className="login-logo" />
      <h2>{role.heading}</h2>
      {/* The school code names the tenant, so an admission number resolves to
          the right school and a login can never land on the wrong one. Required
          for every school-bound login; only the operator has no school. */}
      {!role.hideCode && (
        <input placeholder="School code" value={schoolCode} autoComplete="off"
          required onChange={(e) => setSchoolCode(e.target.value)} />
      )}
      <input placeholder={role.userLabel} value={username}
        autoComplete="username"
        onChange={(e) => setUsername(e.target.value)} />
      <PasswordInput
        placeholder={role.passLabel}
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        autoComplete="current-password"
      />
      <button className="primary" type="submit">Sign in</button>
      <button type="button" className="linkish" onClick={() => setForgot(true)}>
        Forgot password?
      </button>
      {error && <div className="error">{error}</div>}
    </form>
  )
}

const EMPTY_LEARNER = {
  admission_number: '', upi: '', first_name: '', middle_name: '', last_name: '',
  gender: 'M', grade: 7, stream: '', date_of_birth: '', extra: {},
}

function Learners({ grade }) {
  const [learners, setLearners] = useState([])
  const [fields, setFields] = useState([])
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [showInactive, setShowInactive] = useState(false)
  const [editing, setEditing] = useState(null) // learner being edited
  const [form, setForm] = useState(EMPTY_LEARNER)
  const [colMenu, setColMenu] = useState(null) // {type:'field', id} | {type:'add'} | null

  const load = useCallback(() => {
    const q = gradeParam(grade)
    apiGet(
      `/api/learners/?page_size=200${q ? `&${q}` : ''}${showInactive ? '' : '&active=true'}`,
    )
      .then((data) => setLearners(data.results || data))
      .catch((e) => setError(e.message))
    apiGet('/api/learner-fields/?page_size=100')
      .then((d) => setFields(d.results || d))
      .catch(() => setFields([]))
  }, [grade, showInactive])
  useEffect(load, [load])

  const columns = columnApi('/api/learner-fields/', {
    onMessage: setMessage,
    onDone: () => { setColMenu(null); load() },
  })

  const setField = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))
  const setExtra = (key) => (e) => {
    const value = e.target.value
    setForm((f) => ({ ...f, extra: { ...f.extra, [key]: value } }))
  }

  function openEdit(l) {
    setEditing(l)
    setMessage('')
    setForm({
      admission_number: l.admission_number, upi: l.upi || '',
      first_name: l.first_name, middle_name: l.middle_name || '', last_name: l.last_name,
      gender: l.gender, grade: l.grade, stream: l.stream || '',
      date_of_birth: l.date_of_birth || '', extra: l.extra || {},
    })
  }

  async function save(e) {
    e.preventDefault()
    const result = await apiWrite(`/api/learners/${editing.id}/`, form, { method: 'PATCH' })
    setMessage(result.ok ? 'Learner updated.' : `Failed: ${JSON.stringify(result.data)}`)
    if (result.ok) {
      setEditing(null)
      load()
    }
  }

  async function setActive(l, active) {
    const result = await apiWrite(`/api/learners/${l.id}/`, { active }, { method: 'PATCH' })
    setMessage(
      result.ok
        ? `${l.full_name} ${active ? 'reactivated' : 'deactivated'}.`
        : `Could not update: ${JSON.stringify(result.data)}`,
    )
    if (result.ok) load()
  }

  if (error) return <div className="error">{error}</div>

  return (
    <div>
      <p className="muted">
        {learners.length} learners{' '}
        <label style={{ marginLeft: '0.5rem' }}>
          <input
            type="checkbox"
            checked={showInactive}
            onChange={(e) => setShowInactive(e.target.checked)}
          />{' '}
          show deactivated
        </label>
      </p>

      {editing && (
        <div className="card">
          <h3>Edit {editing.full_name}</h3>
          <form onSubmit={save} style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
            <input placeholder="Adm no" value={form.admission_number}
              onChange={setField('admission_number')} style={{ padding: '0.4rem', width: '7rem' }} />
            <input placeholder="UPI" value={form.upi} onChange={setField('upi')}
              style={{ padding: '0.4rem', width: '9rem' }} />
            <input placeholder="First name" value={form.first_name}
              onChange={setField('first_name')} style={{ padding: '0.4rem' }} />
            <input placeholder="Middle name" value={form.middle_name}
              onChange={setField('middle_name')} style={{ padding: '0.4rem' }} />
            <input placeholder="Last name" value={form.last_name}
              onChange={setField('last_name')} style={{ padding: '0.4rem' }} />
            <select value={form.gender} onChange={setField('gender')}>
              <option value="M">Male</option>
              <option value="F">Female</option>
            </select>
            <select value={form.grade} onChange={setField('grade')}>
              {ALL_GRADES.map((g) => (
                <option key={g} value={g}>{gradeLabel(g)}</option>
              ))}
            </select>
            <input placeholder="Stream" value={form.stream} onChange={setField('stream')}
              style={{ padding: '0.4rem', width: '7rem' }} />
            <input type="date" value={form.date_of_birth} onChange={setField('date_of_birth')} />
            {fields.map((f) => (
              <input
                key={f.id}
                placeholder={f.label}
                value={form.extra?.[f.key] || ''}
                onChange={setExtra(f.key)}
                style={{ padding: '0.4rem' }}
              />
            ))}
            <button className="primary" type="submit">Save changes</button>
            <button type="button" onClick={() => setEditing(null)}>Cancel</button>
          </form>
          {message && <p className="muted">{message}</p>}
        </div>
      )}

      {learners.length === 0 ? (
        <p className="muted">No learners in this class.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Adm No</th><th>Name</th><th>Grade</th><th>Stream</th><th>UPI</th><th>Pathway</th>
              <th>Parent / Guardian</th>
              {fields.map((f) => (
                <ColumnHeader
                  key={f.id}
                  field={f}
                  open={colMenu?.type === 'field' && colMenu.id === f.id}
                  onToggle={() =>
                    setColMenu((m) =>
                      m?.type === 'field' && m.id === f.id ? null : { type: 'field', id: f.id },
                    )
                  }
                  onRename={(label) => columns.rename(f, label)}
                  onDelete={() => columns.remove(f)}
                />
              ))}
              <th></th>
              <AddColumnHeader
                open={colMenu?.type === 'add'}
                onToggle={() => setColMenu((m) => (m?.type === 'add' ? null : { type: 'add' }))}
                onAdd={(label) => columns.add(label)}
              />
            </tr>
          </thead>
          <tbody>
            {learners.map((l) => (
              <tr key={l.id} style={!l.active ? { opacity: 0.55 } : undefined}>
                <td>{l.admission_number}</td>
                <td>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <LearnerPhoto photo={l.photo} name={l.full_name} />
                    {l.full_name}
                    {!l.active && <span className="badge offline">Deactivated</span>}
                  </span>
                </td>
                <td>{gradeLabel(l.grade)}</td>
                <td>{l.stream}</td>
                <td>{l.upi}</td>
                <td>{l.pathway_display || '—'}</td>
                <td>
                  {(l.guardians_detail || []).length === 0 && <span className="muted">—</span>}
                  {(l.guardians_detail || []).map((g) => (
                    <div key={g.id}>
                      {g.full_name}
                      {g.relationship ? ` (${g.relationship})` : ''}
                      <div className="muted">
                        <a href={`tel:${g.phone}`}>{g.phone}</a>
                        {g.email ? ` · ${g.email}` : ''}
                      </div>
                    </div>
                  ))}
                </td>
                {fields.map((f) => (
                  <td key={f.id}>{l.extra?.[f.key] || <span className="muted">—</span>}</td>
                ))}
                <td style={{ whiteSpace: 'nowrap' }}>
                  <button onClick={() => openEdit(l)}>Edit</button>{' '}
                  <button onClick={() => setActive(l, !l.active)}>
                    {l.active ? 'Deactivate' : 'Reactivate'}
                  </button>
                </td>
                <td />{/* spacer under the "+" column */}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {!editing && message && <p className="muted">{message}</p>}
    </div>
  )
}

// The Report Card page is the class broadsheet — the whole class on one grid,
// with Excel and printable report-form sets. See Broadsheet.jsx.

// The Fees page is the fee register — structures, invoices, and the
// instalment ledger. See Fees.jsx.

// Sidebar groups, Django-admin style: section header + its items.
// An item with `options` gets a "+" that expands them, so the page can be
// opened already scoped — by class for grade pages, by staff kind for Staff.
// `scopeProp` is the prop name the chosen value is passed down as.
const GRADE_OPTIONS = ALL_GRADES.map((g) => ({ value: g, label: gradeLabel(g) }))
const GRADE_NAV = { scopeProp: 'grade', allLabel: 'All grades', options: GRADE_OPTIONS }
const STAFF_NAV = {
  scopeProp: 'view',
  allLabel: 'All staff',
  options: [
    { value: 'TEACHING', label: 'Teaching' },
    { value: 'NON_TEACHING', label: 'Non-teaching' },
  ],
}

const NAV_SECTIONS = [
  {
    title: 'School',
    items: [
      // The school's own identity sits at the top of its own section — it was
      // under Administration and nobody found it there.
      { name: 'School Profile', label: 'School Profile (Logo, Contacts, Documents)', ownHeading: true },
      { name: 'School', label: 'School (Grades)', ...GRADE_NAV },
      // Staff draws its own heading + "Add staff" button, so the shell skips
      // the generic one.
      { name: 'Staff', label: 'Staff (Teaching / Non-teaching)', ownHeading: true, ...STAFF_NAV },
      { name: 'Staff Register', label: 'Staff Register (Roll-call)', ownHeading: true },
      { name: 'Task Hub', label: 'Task Hub (Duties & Roles)' },
    ],
  },
  {
    title: 'Learners',
    items: [
      { name: 'Learners', label: 'Learners (Students)', ...GRADE_NAV },
      // The admission form draws its own heading; the "+" per grade opens it
      // pre-set to that grade.
      { name: 'Admissions', label: 'Admissions (Admit a learner)', ownHeading: true, ...GRADE_NAV },
      { name: 'Attendance', ...GRADE_NAV },
      { name: 'Report Card', ...GRADE_NAV },
      { name: 'Promotions', label: 'Promotions (End of year)', ownHeading: true },
    ],
  },
  {
    title: 'Academics',
    items: [
      { name: 'Timetable', ...GRADE_NAV },
      { name: 'Schemes Review', ...GRADE_NAV },
      { name: 'Teaching Outcomes', label: 'Teaching Outcomes (Analysis)', ownHeading: true },
      { name: 'Curriculum', label: 'Curriculum Library (RAG)', ownHeading: true },
      { name: 'E-Learning', label: 'E-Learning (Videos, Books)', ownHeading: true },
    ],
  },
  {
    title: 'Facilities',
    items: [
      // Options are loaded from the API — one per facility the school has.
      {
        name: 'Facilities',
        label: 'Facilities (Transport, Dorms…)',
        ownHeading: true,
        scopeProp: 'facility',
        allLabel: 'All facilities',
        dynamicOptions: 'facilityCategories',
        options: [],
      },
    ],
  },
  { title: 'Finance', items: [{ name: 'Fees', ...GRADE_NAV }] },
  {
    title: 'Communication',
    items: [
      // The "+" per class opens the composer already aimed at that class.
      { name: 'Messages', label: 'Messages (SMS & WhatsApp)', ownHeading: true, ...GRADE_NAV },
    ],
  },
  {
    title: 'Administration',
    items: [
      { name: 'Audit Log', label: 'Audit Log (Who changed what)', ownHeading: true },
      { name: 'Subscription', label: 'Subscription (Billing)', ownHeading: true },
    ],
  },
]

const ALL_ITEMS = NAV_SECTIONS.flatMap((s) => s.items)

// /admin/<slug> ↔ tab name, e.g. /admin/school-profile ↔ "School Profile".
const SLUG_TO_TAB = Object.fromEntries(ALL_ITEMS.map((i) => [slugify(i.name), i.name]))

const TABS = {
  School: SchoolStructure,
  Staff: Staff,
  'Staff Register': StaffRollCall,
  Learners: Learners,
  Admissions: Admission,
  Promotions: Promotions,
  Attendance: Attendance,
  'Report Card': Broadsheet,
  'Task Hub': TaskHub,
  Fees: Fees,
  Messages: Messaging,
  'School Profile': SchoolProfile,
  Timetable: Timetable,
  'Schemes Review': SchemesReview,
  Curriculum: Curriculum,
  'Teaching Outcomes': Analysis,
  'E-Learning': (props) => <Learning canCurate isOperator={false} {...props} />,
  'Audit Log': Audit,
  Subscription: Subscription,
  Facilities: Facilities,
}

export default function App() {
  const [authed, setAuthed] = useState(() => Boolean(getToken()))
  const [me, setMe] = useState(null)
  const [tab, setTab] = useState('Learners')
  const [scope, setScope] = useState(null) // null = unscoped (all)
  const [expanded, setExpanded] = useState({})
  const [navFilter, setNavFilter] = useState('')
  const [facilityOptions, setFacilityOptions] = useState([])
  const [customSections, setCustomSections] = useState([])
  const [newSection, setNewSection] = useState('')
  const [addingSection, setAddingSection] = useState(false)
  // Bumped by pages that change what the sidebar lists (e.g. adding a facility).
  const [navVersion, setNavVersion] = useState(0)
  const [online, setOnline] = useState(navigator.onLine)
  const [queued, setQueued] = useState(queuedCount())
  const [rejected, setRejected] = useState(rejectedWrites())
  const [showQueue, setShowQueue] = useState(false)
  const [syncNote, setSyncNote] = useState('')
  const path = usePath()

  // Signed out → the sign-in page. Three paths are allowed to stand rather than
  // being bounced to /login: /login itself, the operator's own /operator/login,
  // and /verify/<token>, which is the password-reset link a signed-out user
  // opens from their email.
  useEffect(() => {
    const p = window.location.pathname
    const allowed = p === '/login' || p === '/operator/login' || p.startsWith('/verify/')
    if (!authed && !allowed) {
      goTo('/login', { replace: true })
    }
  }, [authed])

  // The address bar and the open tab say the same thing, in both directions:
  // a pasted /<school>/admin/fees opens Fees; landing on the wrong portal's
  // path (or a stale schoolless one) redirects to your own /<school>/... .
  useEffect(() => {
    if (!authed || !me || me.must_change_password) return
    const base = basePathFor(me)          // e.g. /demo-junior-school/admin
    const isAdmin = portalFor(me) === 'admin'
    if (!isAdmin) {
      // Teacher, staff, parent and operator portals keep their own tab state
      // in React, not the URL, so they sit at exactly their base — this also
      // normalises the operator away from /operator/login after signing in.
      if (path !== base) goTo(base, { replace: true })
      return
    }
    if (!path.startsWith(base)) {
      goTo(`${base}/${slugify(tab)}`, { replace: true })
      return
    }
    const segment = path.slice(base.length).replace(/^\/+/, '').split('/')[0]
    const name = SLUG_TO_TAB[segment]
    if (name && name !== tab) {
      setTab(name)
      setScope(null)
    } else if (!segment) {
      goTo(`${base}/${slugify(tab)}`, { replace: true })
    }
  }, [authed, me, path]) // eslint-disable-line react-hooks/exhaustive-deps

  const refreshQueue = useCallback(() => {
    setQueued(queuedCount())
    setRejected(rejectedWrites())
  }, [])

  useEffect(() => {
    const up = () => setOnline(true)
    const down = () => setOnline(false)
    window.addEventListener('online', up)
    window.addEventListener('offline', down)
    const stop = startQueueFlusher(refreshQueue)
    return () => {
      window.removeEventListener('online', up)
      window.removeEventListener('offline', down)
      stop()
    }
  }, [refreshQueue])

  // A revoked or expired token drops straight back to the login screen instead
  // of leaving every panel showing an unexplained failure.
  useEffect(() => {
    setUnauthorizedHandler(() => setAuthed(false))
    return () => setUnauthorizedHandler(null)
  }, [])

  // Facility nav entries mirror the school's own categories, with a trailing
  // entry for creating a new one.
  useEffect(() => {
    if (!authed || !me || me.role === 'PARENT') return
    apiGet('/api/facility-categories/?page_size=100')
      .then((d) =>
        setFacilityOptions([
          // Categories filed under a custom heading show there instead.
          ...(d.results || d)
            .filter((c) => !c.section)
            .map((c) => ({
              value: c.id,
              label: `${c.name}${c.facility_count ? ` (${c.facility_count})` : ''}`,
            })),
          { value: ADD_CATEGORY, label: '+ Add category' },
        ]),
      )
      .catch(() => setFacilityOptions([]))
    apiGet('/api/nav-sections/?page_size=50')
      .then((d) => setCustomSections(d.results || d))
      .catch(() => setCustomSections([]))
  }, [authed, me, tab, navVersion])

  async function addSection(e) {
    e.preventDefault()
    if (!newSection.trim()) return
    const result = await apiWrite('/api/nav-sections/', {
      name: newSection,
      order: customSections.length,
    })
    if (result.ok) {
      setNewSection('')
      setAddingSection(false)
      setNavVersion((v) => v + 1)
    }
  }

  useEffect(() => {
    if (!authed) {
      setMe(null)
      return
    }
    apiGet('/api/me/')
      .then(setMe)
      .catch(() => {
        // Stale/invalid token: force re-login.
        clearToken()
        setAuthed(false)
      })
  }, [authed])

  // The email reset link lands here while signed out. Works before any login.
  const resetToken = path.startsWith('/verify/') ? path.slice('/verify/'.length) : null
  if (!authed && resetToken) {
    return <ResetByLink token={resetToken} onDone={() => goTo('/login', { replace: true })} />
  }
  if (!authed) return <Login onLogin={() => setAuthed(true)} />
  if (!me) return <p className="muted" style={{ padding: '2rem' }}>Loading…</p>
  // An admin-issued password is a handover credential. Nothing else in
  // the app is reachable until it has been replaced.
  if (me.must_change_password) {
    return (
      <ForcedPasswordChange
        name={me.full_name}
        onDone={() => setMe({ ...me, must_change_password: false })}
      />
    )
  }

  // The platform operator lives above all schools — a different app entirely.
  if (me.is_operator) return <Operator me={me} />

  const isParent = me.role === 'PARENT'
  const isTeacher = me.role === 'TEACHER'
  const isSupport = me.role === 'SUPPORT'
  const isStaffUI = !isParent && !isTeacher && !isSupport
  const Active = TABS[tab]

  const title = isParent
    ? 'Parent Portal'
    : isTeacher
      ? 'Teacher Portal'
      : isSupport
        ? 'Staff Portal'
        : 'School Management'

  const withOptions = (item) =>
    item.dynamicOptions === 'facilityCategories'
      ? { ...item, options: facilityOptions }
      : item

  const filter = navFilter.trim().toLowerCase()
  const sections = NAV_SECTIONS.map((section) => ({
    ...section,
    items: section.items
      .filter((item) => (item.label || item.name).toLowerCase().includes(filter))
      .map(withOptions),
  })).filter((section) => section.items.length > 0)

  const activeSection = NAV_SECTIONS.find((s) => s.items.some((i) => i.name === tab))
  const activeItem = ALL_ITEMS.map(withOptions).find((i) => i.name === tab)
  const scopeLabel =
    scope === null
      ? null
      : activeItem?.options?.find((o) => o.value === scope)?.label ?? String(scope)
  const scopeProps = activeItem?.scopeProp ? { [activeItem.scopeProp]: scope } : {}

  const openTab = (name, nextScope = null) => {
    setTab(name)
    setScope(nextScope)
    if (isStaffUI) goTo(`${basePathFor(me)}/${slugify(name)}`)
  }

  return (
    <div className="admin-shell">
      <header className="topbar">
        <h1 className="brand-h1">
          <img src="/icon.svg" alt="" className="brand-mark" />
          <span className="wm"><span className="wm-s">Shule</span><span className="wm-n">Nest</span></span>
          <span className="brand-sub">{title}</span>
        </h1>
        <div className="userlinks">
          {/* Every staff login gets the bell — a supervisor's message lands in
              the teacher and support portals, not just the admin shell. */}
          {!isParent && <Notifications />}
          <span className={`badge ${online ? 'online' : 'offline'}`}>
            {online ? 'Online' : 'Offline'}
          </span>
          {queued > 0 && (
            <button className="badge queued" title="See what has not synced"
              onClick={() => setShowQueue((s) => !s)}>
              {queued} pending sync
            </button>
          )}
          {rejected.length > 0 && (
            <span className="badge offline">{rejected.length} failed to sync</span>
          )}
          <span>
            Welcome, <b>{(me.full_name || me.username).toUpperCase()}</b>.
          </span>
          <button
            onClick={() => {
              clearToken()
              setAuthed(false)
            }}
          >
            Log out
          </button>
        </div>
      </header>

      {showQueue && queued > 0 && (
        <div className="sync-failures">
          <b>{queued} change{queued > 1 ? 's are' : ' is'} waiting to sync.</b>
          <p className="muted" style={{ margin: '0.3rem 0' }}>
            These were saved on this device when the server could not be
            reached. They retry automatically; a change that keeps failing is
            moved to the failures list after five attempts.
          </p>
          <ul>
            {queuedWrites().slice(0, 8).map((q, i) => (
              <li key={i}>
                {q.method} {q.path}
                {q.attempts ? ` — ${q.attempts} attempt${q.attempts > 1 ? 's' : ''}` : ''}
              </li>
            ))}
          </ul>
          <button className="primary" onClick={async () => {
            const { flushed, rejected: failed } = await flushQueue()
            refreshQueue()
            setSyncNote(
              flushed || failed
                ? `${flushed} synced, ${failed} could not be saved.`
                : 'Still unreachable — they stay queued.',
            )
          }}>Retry now</button>{' '}
          <button onClick={() => {
            if (!window.confirm(
              `Discard ${queued} unsynced change${queued > 1 ? 's' : ''}? `
              + 'They will not reach the server.',
            )) return
            discardQueue()
            refreshQueue()
            setShowQueue(false)
          }}>Discard them</button>
          {syncNote && <span className="muted"> {syncNote}</span>}
        </div>
      )}

      {rejected.length > 0 && (
        <div className="sync-failures">
          <b>{rejected.length} saved-offline change{rejected.length > 1 ? 's were' : ' was'} rejected
          by the server and did not go through.</b>
          <ul>
            {rejected.slice(0, 5).map((r, i) => (
              <li key={i}>
                {r.method} {r.path} — {r.status}
                {r.detail?.detail ? `: ${r.detail.detail}` : ''}
              </li>
            ))}
          </ul>
          <button
            onClick={() => {
              clearRejectedWrites()
              setRejected([])
            }}
          >
            Dismiss — I'll re-enter these
          </button>
        </div>
      )}

      {isStaffUI && <PlatformAnnouncements />}

      <div className="breadcrumbs">
        {isStaffUI ? (
          <>
            Home{activeSection ? ` › ${activeSection.title}` : ''} › {tab}
            {scopeLabel && ` › ${scopeLabel}`}
          </>
        ) : (
          <>Home › {me.school || 'My school'}</>
        )}
      </div>

      <div className="admin-body">
        {isStaffUI && (
          <aside className="sidenav">
            <input
              className="navfilter"
              placeholder="Start typing to filter…"
              value={navFilter}
              onChange={(e) => setNavFilter(e.target.value)}
            />
            {sections.map((section) => (
              <div className="nav-section" key={section.title}>
                <div className="nav-section-title">{section.title}</div>
                {section.items.map((item) => {
                  const isOpen = Boolean(expanded[item.name])
                  return (
                    <div key={item.name}>
                      <div className="nav-item-row">
                        <button
                          className={`nav-item${tab === item.name ? ' active' : ''}`}
                          onClick={() => openTab(item.name)}
                        >
                          {item.label || item.name}
                        </button>
                        {item.options && (
                          <button
                            className="nav-plus"
                            title={isOpen ? 'Collapse' : 'Expand'}
                            aria-label={`${isOpen ? 'Collapse' : 'Expand'} ${item.name}`}
                            aria-expanded={isOpen}
                            onClick={() =>
                              setExpanded((prev) => ({ ...prev, [item.name]: !prev[item.name] }))
                            }
                          >
                            {isOpen ? '−' : '+'}
                          </button>
                        )}
                      </div>
                      {item.options && isOpen && (
                        <div className="nav-grades">
                          <button
                            className={tab === item.name && scope === null ? 'active' : ''}
                            onClick={() => openTab(item.name, null)}
                          >
                            {item.allLabel}
                          </button>
                          {item.options.map((opt) => (
                            <button
                              key={String(opt.value)}
                              className={tab === item.name && scope === opt.value ? 'active' : ''}
                              onClick={() => openTab(item.name, opt.value)}
                            >
                              {opt.label}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            ))}
            {/* Headings the admin added, each holding its facility categories */}
            {customSections
              .filter((s) => !filter || s.name.toLowerCase().includes(filter))
              .map((section) => (
                <div className="nav-section" key={`custom-${section.id}`}>
                  <div className="nav-section-title">{section.name}</div>
                  {section.categories.length === 0 && (
                    <div className="nav-item-row">
                      <button
                        className="nav-item"
                        onClick={() => openTab('Facilities', ADD_CATEGORY)}
                      >
                        <span className="muted">Add a category…</span>
                      </button>
                    </div>
                  )}
                  {section.categories.map((c) => (
                    <div className="nav-item-row" key={c.id}>
                      <button
                        className={`nav-item${tab === 'Facilities' && scope === c.id ? ' active' : ''}`}
                        onClick={() => openTab('Facilities', c.id)}
                      >
                        {c.name}
                        {c.facility_count ? ` (${c.facility_count})` : ''}
                      </button>
                    </div>
                  ))}
                </div>
              ))}

            {/* Add a heading of your own */}
            {addingSection ? (
              <form onSubmit={addSection} className="nav-add-section">
                <input
                  autoFocus
                  className="navfilter"
                  placeholder="Section name e.g. Boarding"
                  value={newSection}
                  onChange={(e) => setNewSection(e.target.value)}
                  style={{ marginBottom: '0.4rem' }}
                />
                <div style={{ display: 'flex', gap: '0.35rem' }}>
                  <button className="primary" type="submit">Add</button>
                  <button type="button" onClick={() => { setAddingSection(false); setNewSection('') }}>
                    Cancel
                  </button>
                </div>
              </form>
            ) : (
              <button className="nav-add-btn" onClick={() => setAddingSection(true)}>
                + Add section
              </button>
            )}

            {sections.length === 0 && <p className="muted">No matches.</p>}
          </aside>
        )}

        <main className={`admin-content${isStaffUI ? '' : ' narrow'}`}>
          {isParent ? (
            <ParentPortal />
          ) : isSupport ? (
            <SupportPortal />
          ) : isTeacher ? (
            <TeacherPortal onQueueChange={refreshQueue} />
          ) : (
            <>
              {!activeItem?.ownHeading && (
                <h2 style={{ marginTop: 0 }}>
                  {tab}
                  {scopeLabel && (
                    <>
                      {' — '}
                      <span style={{ color: '#2b6cb0' }}>{scopeLabel}</span>{' '}
                      <button className="clear-grade" onClick={() => setScope(null)}>
                        {activeItem?.allLabel
                          ? `show ${activeItem.allLabel.toLowerCase()}`
                          : 'show all'}
                      </button>
                    </>
                  )}
                </h2>
              )}
              <Active
                {...scopeProps}
                onQueueChange={refreshQueue}
                onNavRefresh={() => setNavVersion((v) => v + 1)}
              />
            </>
          )}
        </main>
      </div>
    </div>
  )
}
