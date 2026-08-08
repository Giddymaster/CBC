import { useCallback, useEffect, useState } from 'react'
import { apiGet, apiWrite } from './api.js'
import { useAnchoredMenu } from './columns.jsx'
import { ALL_GRADES, gradeLabel } from './format.js'

const DAY_NAMES = { 1: 'Mon', 2: 'Tue', 3: 'Wed', 4: 'Thu', 5: 'Fri' }
const TODAY_LABEL = { P: 'Present', A: 'Absent', L: 'Late', E: 'Excused' }
const TODAY_BADGE = { P: 'online', A: 'offline', L: 'queued', E: 'queued' }

function TodayBadge({ status }) {
  if (!status) return <span className="muted">Not marked</span>
  return <span className={`badge ${TODAY_BADGE[status]}`}>{TODAY_LABEL[status]}</span>
}

function TimetableGrid({ lessons, showTeacher }) {
  if (!lessons.length) return <p className="muted">No timetable yet — generate one from the Timetable tab.</p>
  const periods = [...new Set(lessons.map((l) => l.period))].sort((a, b) => a - b)
  const times = Object.fromEntries(lessons.map((l) => [l.period, `${l.start}–${l.end}`]))
  const grid = {}
  for (const l of lessons) {
    grid[l.period] = grid[l.period] || {}
    grid[l.period][l.day] = l
  }
  return (
    <table>
      <thead>
        <tr>
          <th>Day</th>
          {periods.map((p) => (
            <th key={p}>P{p}<div className="muted">{times[p]}</div></th>
          ))}
        </tr>
      </thead>
      <tbody>
        {Object.entries(DAY_NAMES).map(([day, label]) => (
          <tr key={day}>
            <td><b>{label}</b></td>
            {periods.map((p) => {
              const l = grid[p]?.[day]
              return (
                <td key={p}>
                  {l && (
                    <>
                      {l.learning_area}
                      <div className="muted">
                        {showTeacher ? l.teacher : `${gradeLabel(l.grade)}${l.stream}`}
                        {l.room ? ` · ${l.room}` : ''}
                      </div>
                    </>
                  )}
                </td>
              )
            })}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function LearnerPhoto({ photo, name, large }) {
  const initials = (name || '')
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0].toUpperCase())
    .join('')
  if (photo) {
    return (
      <img
        src={photo}
        alt={name}
        className={large ? 'learner-photo-lg' : 'learner-photo'}
      />
    )
  }
  return (
    <span className={large ? 'learner-photo-lg-empty' : 'learner-photo-empty'}>
      {initials || '?'}
    </span>
  )
}

// The admission record, minus anything empty — a mostly-blank grid of dashes
// tells the reader nothing.
function AdmissionDetails({ admission }) {
  if (!admission) return null
  const rows = [
    ['Date of birth', admission.date_of_birth],
    ['Admitted', admission.admission_date],
    ['Admitted by', admission.admitted_by],
    ['Birth cert no', admission.birth_certificate_no],
    ['Nationality', admission.nationality],
    ['Religion', admission.religion],
    ['Home', [admission.home_address, admission.ward, admission.subcounty, admission.county]
      .filter(Boolean).join(', ')],
    ['Boarding', admission.residence],
    ['Travels by', [admission.transport, admission.bus_route].filter(Boolean).join(' · ')],
    ['Previous school', admission.previous_school],
    ['Blood group', admission.blood_group],
    ['NHIF', admission.nhif_number],
    ['Allergies', admission.allergies],
    ['Chronic conditions', admission.chronic_conditions],
    ['Medication', admission.medication],
    ['Special needs', admission.special_needs],
    [
      'Emergency contact',
      [
        admission.emergency_contact_name,
        admission.emergency_contact_phone,
        admission.emergency_contact_relationship
          ? `(${admission.emergency_contact_relationship})`
          : '',
      ].filter(Boolean).join(' '),
    ],
    ['Notes', admission.admission_notes],
  ].filter(([, value]) => value !== null && value !== undefined && value !== '')

  if (!rows.length) return null

  const medical = new Set([
    'Blood group', 'Allergies', 'Chronic conditions', 'Medication', 'Special needs',
  ])

  return (
    <div className="profile-grid" style={{ marginTop: '0.6rem' }}>
      {rows.map(([label, value]) => (
        <div className="profile-field" key={label}>
          <span className="profile-label">{label}</span>
          <span
            className="profile-value"
            style={medical.has(label) ? { color: '#9b2c2c' } : undefined}
          >
            {value}
          </span>
        </div>
      ))}
    </div>
  )
}

function StudentProfile({ learnerId, onBack }) {
  const [profile, setProfile] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    apiGet(`/api/learners/${learnerId}/profile/`).then(setProfile).catch((e) => setError(e.message))
  }, [learnerId])

  if (error) return <div className="error">{error}</div>
  if (!profile) return <p className="muted">Loading profile…</p>

  const learner = profile.report_card.learner
  const areas = profile.report_card.learning_areas
  const att = profile.attendance

  return (
    <div>
      <p><button onClick={onBack}>← Back to grade</button></p>
      <div className="card">
        <div style={{ display: 'flex', gap: '1.2rem', alignItems: 'flex-start' }}>
          <LearnerPhoto photo={profile.photo} name={learner.name} large />
          <div style={{ flex: 1 }}>
            <h3 style={{ marginTop: 0 }}>{learner.name} — {learner.admission_number}</h3>
            <p className="muted">
              {gradeLabel(learner.grade)} {learner.stream} · UPI {learner.upi || '—'}
              {learner.pathway ? ` · ${learner.pathway}` : ''}
            </p>
            <AdmissionDetails admission={profile.admission} />
          </div>
        </div>
        <p>
          <b>Guardians:</b>{' '}
          {profile.guardians.length === 0 && <span className="muted">none on record</span>}
          {profile.guardians.map((g) => (
            <span key={g.id}>
              {g.full_name}{g.relationship ? ` (${g.relationship})` : ''} —{' '}
              <a href={`tel:${g.phone}`}>{g.phone}</a>{' '}
            </span>
          ))}
        </p>
        <p>
          <b>Fees:</b> balance KES {profile.fees.total_balance}{' '}
          {profile.fees.invoices.map((inv) => (
            <span key={inv.id} className={`badge ${inv.status === 'PAID' ? 'online' : 'queued'}`}>
              {inv.status}
            </span>
          ))}
        </p>
        <p>
          <b>Attendance:</b> {att.present} present · {att.absent} absent · {att.late} late ·{' '}
          {att.excused} excused
        </p>
      </div>

      <div className="card">
        <h3>Subject scores</h3>
        {Object.keys(areas).length === 0 && <p className="muted">No assessment records yet.</p>}
        {Object.keys(areas).length > 0 && (
          <table>
            <thead>
              <tr><th>Learning area</th><th>Assessment</th><th>Marks</th><th>Level</th></tr>
            </thead>
            <tbody>
              {Object.entries(areas).flatMap(([area, kinds]) =>
                Object.entries(kinds).map(([kind, s]) => (
                  <tr key={area + kind}>
                    <td>{area}</td>
                    <td>{kind}</td>
                    <td>{s.marks} / {s.max_marks}</td>
                    <td><span className={`level ${s.competency_level}`}>{s.competency_level}</span></td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

// Admin control to set (or clear) the class teacher for one class.
function ClassTeacherPicker({ classGroupId, currentName, onSaved }) {
  const [teachers, setTeachers] = useState([])
  const [choice, setChoice] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => {
    apiGet('/api/teachers/?page_size=200').then((d) => setTeachers(d.results || d))
  }, [])

  async function save() {
    setBusy(true)
    setMessage('')
    const result = await apiWrite(
      `/api/class-groups/${classGroupId}/`,
      { class_teacher: choice === '' ? null : Number(choice) },
      { method: 'PATCH' },
    )
    setBusy(false)
    if (result.ok) {
      setMessage('Class teacher updated.')
      onSaved()
    } else {
      setMessage(
        result.data?.detail || `Could not update: ${JSON.stringify(result.data)}`,
      )
    }
  }

  return (
    <p style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
      <b>{currentName ? 'Change class teacher:' : 'Assign class teacher:'}</b>
      <select value={choice} onChange={(e) => setChoice(e.target.value)}>
        <option value="">— none —</option>
        {teachers.map((t) => (
          <option key={t.id} value={t.id}>
            {t.name || t.user} (TSC {t.tsc_number})
          </option>
        ))}
      </select>
      <button className="primary" onClick={save} disabled={busy}>
        {busy ? 'Saving…' : 'Save'}
      </button>
      {message && <span className="muted">{message}</span>}
    </p>
  )
}

// Who teaches what in this class. One row = teacher × learning area × stream ×
// lessons/week — the LessonRequirement the timetable generator places, and the
// same assignment that puts the class into that teacher's portal: their score
// entry, schemes of work and lesson plans all follow from here.
function TeachingAssignments({ grade, streams, onMessage }) {
  const [reqs, setReqs] = useState(null)
  const [areas, setAreas] = useState([])
  const [teachers, setTeachers] = useState([])
  const [form, setForm] = useState({
    learning_area: '', teacher: '', stream: '', lessons_per_week: 5,
  })

  const load = useCallback(() => {
    apiGet(`/api/timetable/requirements/?grade=${grade}&page_size=200`)
      .then((d) => setReqs(d.results || d))
      .catch(() => setReqs([]))
  }, [grade])
  useEffect(load, [load])
  useEffect(() => {
    apiGet('/api/learning-areas/?page_size=200')
      .then((d) => setAreas(d.results || d)).catch(() => {})
    apiGet('/api/teachers/?page_size=200')
      .then((d) => setTeachers(d.results || d)).catch(() => {})
  }, [])

  // Only the areas this grade actually teaches (School (Grades) overview).
  const gradeAreas = areas.filter((a) => a.grades.includes(grade))

  // A phased teacher stays in their section: pre-primary PG-PP2, primary
  // G1-G6, junior G7-G9. Unphased staff (leadership, floaters) appear always.
  const phaseFor = grade <= 0 ? 'PRE_PRIMARY' : grade <= 6 ? 'PRIMARY' : 'JUNIOR'
  const eligibleTeachers = teachers.filter(
    (t) => !t.phase || t.phase === phaseFor,
  )

  async function add(e) {
    e.preventDefault()
    if (!form.learning_area || !form.teacher) {
      onMessage('Pick a learning area and the teacher taking it.')
      return
    }
    const res = await apiWrite('/api/timetable/requirements/', {
      grade,
      learning_area: Number(form.learning_area),
      teacher: Number(form.teacher),
      stream: form.stream,
      lessons_per_week: Number(form.lessons_per_week) || 5,
    })
    if (res.ok) {
      setForm({ learning_area: '', teacher: '', stream: '', lessons_per_week: 5 })
      onMessage('')
      load()
    } else {
      onMessage(res.data?.detail || JSON.stringify(res.data) || 'Could not assign.')
    }
  }

  async function remove(r) {
    if (!window.confirm(`Remove ${r.learning_area_name} from ${r.teacher_name}?`)) return
    const res = await apiWrite(`/api/timetable/requirements/${r.id}/`, {}, { method: 'DELETE' })
    if (!res.ok) onMessage('Could not remove that assignment.')
    load()
  }

  if (!reqs) return null

  return (
    <div className="card">
      <h3>Teaching assignments</h3>
      <p className="muted">
        Who teaches what in this class. The timetable is generated from these, and
        each teacher's portal — score entry, schemes, lesson plans — follows them.
        {grade <= 3 && (
          <>
            {' '}In {gradeLabel(grade)} the class teacher takes the class through
            every learning area, so assign them to each — the timetable generator
            covers G4–G9 only.
          </>
        )}
      </p>
      <form onSubmit={add}
        style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center',
                 marginBottom: '0.6rem' }}>
        <select value={form.learning_area}
          onChange={(e) => setForm({ ...form, learning_area: e.target.value })}>
          <option value="">Learning area…</option>
          {gradeAreas.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
        <select value={form.teacher}
          onChange={(e) => setForm({ ...form, teacher: e.target.value })}>
          <option value="">Teacher…</option>
          {eligibleTeachers.map((t) => (
            <option key={t.id} value={t.id}>{t.name || t.user} (TSC {t.tsc_number})</option>
          ))}
        </select>
        {streams.length > 0 && (
          <select value={form.stream}
            onChange={(e) => setForm({ ...form, stream: e.target.value })}>
            <option value="">Whole grade</option>
            {streams.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        )}
        <label className="muted">
          Lessons/week{' '}
          <input type="number" min="1" max="14" value={form.lessons_per_week}
            style={{ width: '4rem' }}
            onChange={(e) => setForm({ ...form, lessons_per_week: e.target.value })} />
        </label>
        <button className="primary" type="submit">Assign</button>
      </form>
      {gradeAreas.length === 0 && (
        <p className="muted">
          This grade has no learning areas yet — tick them on the School (Grades)
          overview first.
        </p>
      )}
      {reqs.length === 0 ? (
        <p className="muted">Nothing assigned yet.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Learning area</th><th>Stream</th><th>Teacher</th>
              <th>Lessons/week</th><th></th>
            </tr>
          </thead>
          <tbody>
            {reqs.map((r) => (
              <tr key={r.id}>
                <td><b>{r.learning_area_name}</b></td>
                <td>{r.stream || <span className="muted">whole grade</span>}</td>
                <td>{r.teacher_name}</td>
                <td>{r.lessons_per_week}</td>
                <td>
                  <button onClick={() => remove(r)}>Remove</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function GradeDetail({ grade, label, onBack }) {
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [sortBy, setSortBy] = useState('admission_number')
  const [genderFilter, setGenderFilter] = useState('ALL')
  const [profileId, setProfileId] = useState(null)

  const loadDetail = useCallback(() => {
    apiGet(`/api/school/grades/${grade}/`).then(setDetail).catch((e) => setError(e.message))
  }, [grade])
  useEffect(loadDetail, [loadDetail])

  if (error) return <div className="error">{error}</div>
  if (!detail) return <p className="muted">Loading {label}…</p>
  if (profileId) return <StudentProfile learnerId={profileId} onBack={() => setProfileId(null)} />

  const students = detail.students
    .filter((s) => genderFilter === 'ALL' || s.gender === genderFilter)
    .sort((a, b) => String(a[sortBy]).localeCompare(String(b[sortBy])))

  return (
    <div>
      <p>
        <button onClick={onBack}>← All grades</button>{' '}
        <b>{detail.label}</b>{' '}
        <span className="muted">
          {detail.totals.students} learners ({detail.totals.male}M / {detail.totals.female}F) ·{' '}
          today: {detail.totals.present_today} present, {detail.totals.absent_today} absent,{' '}
          {detail.totals.unmarked_today} not marked
        </span>
      </p>

      {detail.class_teachers.map((ct) => (
        <div className="card" key={ct.stream || 'main'}>
          <h3>Class teacher{ct.stream ? ` — ${detail.label} ${ct.stream}` : ''}</h3>
          {!ct.name && <p className="muted">No class teacher assigned.</p>}
          {ct.class_group_id && (
            <ClassTeacherPicker
              classGroupId={ct.class_group_id}
              currentName={ct.name}
              onSaved={loadDetail}
            />
          )}
          {ct.name && (
            <>
              <p>
                <b>{ct.name}</b> (TSC {ct.tsc_number}){' '}
                <TodayBadge status={ct.present_today} />{' '}
                <span className={`badge ${ct.roll_call_taken_today ? 'online' : 'queued'}`}>
                  {ct.roll_call_taken_today ? 'Roll-call taken today' : 'Roll-call pending'}
                </span>
              </p>
              <p>
                <b>Lessons:</b>{' '}
                {(ct.lessons || []).length === 0
                  ? '—'
                  : ct.lessons.map((l) => `${l.subject} (${l.grade_label})`).join(', ')}
              </p>
              <p>
                <b>Schemes of work:</b>{' '}
                {ct.schemes_of_work.length === 0 && <span className="muted">none</span>}
                {ct.schemes_of_work.map((s) => (
                  <span key={s.id}>
                    {s.learning_area} T{s.term}{' '}
                    <span className={`badge ${s.status === 'APPROVED' ? 'online' : s.status === 'REJECTED' ? 'offline' : 'queued'}`}>
                      {s.status}
                    </span>{' '}
                  </span>
                ))}
              </p>
              <details>
                <summary>Teacher timetable ({ct.timetable.length} lessons/week)</summary>
                <TimetableGrid lessons={ct.timetable} showTeacher={false} />
              </details>
            </>
          )}
        </div>
      ))}

      {message && <p className="error">{message}</p>}
      <TeachingAssignments
        grade={grade}
        streams={[...new Set(detail.class_teachers.map((ct) => ct.stream).filter(Boolean))]}
        onMessage={setMessage}
      />

      <div className="card">
        <h3>Students</h3>
        <p>
          Sort by{' '}
          <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
            <option value="admission_number">Admission no</option>
            <option value="name">Name</option>
          </select>{' '}
          Gender{' '}
          <select value={genderFilter} onChange={(e) => setGenderFilter(e.target.value)}>
            <option value="ALL">All</option>
            <option value="M">Male</option>
            <option value="F">Female</option>
          </select>
        </p>
        <table>
          <thead>
            <tr>
              <th>Adm No</th><th>Name</th><th>Gender</th><th>Stream</th><th>Today</th><th></th>
            </tr>
          </thead>
          <tbody>
            {students.map((s) => (
              <tr key={s.id}>
                <td>{s.admission_number}</td>
                <td>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <LearnerPhoto photo={s.photo} name={s.name} />
                    {s.name}
                  </span>
                </td>
                <td>{s.gender}</td>
                <td>{s.stream}</td>
                <td><TodayBadge status={s.today} /></td>
                <td><button onClick={() => setProfileId(s.id)}>Profile</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h3>Class timetable</h3>
        <TimetableGrid lessons={detail.timetable} showTeacher={true} />
      </div>
    </div>
  )
}

// The streams a grade runs (its ClassGroup rows). Adding one here makes it
// selectable on admission, class-teacher assignment and the timetable.
function StreamsCell({ grade, classes, onChanged, onMessage }) {
  const [adding, setAdding] = useState(false)
  const [name, setName] = useState('')

  async function add(e) {
    e.preventDefault()
    const res = await apiWrite('/api/class-groups/', { grade, stream: name.trim() })
    if (res.ok) {
      setName('')
      setAdding(false)
      onChanged()
    } else {
      onMessage(res.data?.detail || JSON.stringify(res.data) || 'Could not add stream.')
    }
  }

  async function remove(c) {
    const label = c.stream || '(no stream name)'
    if (!window.confirm(`Remove ${label} from ${gradeLabel(grade)}? Learners keep their records.`)) return
    const res = await apiWrite(`/api/class-groups/${c.id}/`, {}, { method: 'DELETE' })
    if (!res.ok) onMessage('Could not remove that stream.')
    onChanged()
  }

  return (
    <span className="streams-cell">
      {classes.map((c) => (
        <span key={c.id} className="stream-chip">
          {c.stream || '—'}
          <button type="button" title="Remove stream" onClick={() => remove(c)}>×</button>
        </span>
      ))}
      {adding ? (
        <form onSubmit={add} style={{ display: 'inline-flex', gap: '0.3rem' }}>
          <input autoFocus placeholder="e.g. North" value={name}
            onChange={(e) => setName(e.target.value)}
            style={{ padding: '0.2rem 0.4rem', width: '6.5rem' }} />
          <button className="primary" type="submit">Add</button>
          <button type="button" onClick={() => setAdding(false)}>×</button>
        </form>
      ) : (
        <button type="button" className="grade-chip" onClick={() => setAdding(true)}>
          + stream
        </button>
      )}
    </span>
  )
}

// Which learning areas the grade teaches — the same fact the Learning areas
// card edits, seen from the grade's side.
function GradeAreasCell({ grade, areas, onToggle }) {
  const [open, setOpen] = useState(false)
  const [anchorRef, menuStyle] = useAnchoredMenu(open, 260)
  const inGrade = areas.filter((a) => a.grades.includes(grade))
  const summary = inGrade.length
    ? `${inGrade.length} — ${inGrade.slice(0, 3).map((a) => a.name).join(', ')}${inGrade.length > 3 ? '…' : ''}`
    : '—'
  return (
    <>
      <button ref={anchorRef} type="button" className="cell-view" title="Click to choose"
        onClick={() => setOpen((o) => !o)}>
        {summary}
      </button>
      {open && (
        <div className="col-menu scrolly" style={menuStyle}>
          {areas.length === 0 && (
            <p className="muted" style={{ margin: 0 }}>
              No learning areas defined — load the MoE set below, or add your own.
            </p>
          )}
          {areas.map((a) => (
            <label key={a.id} className="subj-choice">
              <input type="checkbox" checked={a.grades.includes(grade)}
                onChange={() => onToggle(a, grade)} />
              {a.name}
            </label>
          ))}
          <button type="button" onClick={() => setOpen(false)}>Close</button>
        </div>
      )}
    </>
  )
}

// Which learning areas the school teaches, and in which grades. This list
// feeds assessments, teacher subjects, schemes of work and the timetable.
function LearningAreasCard({ areas, onChanged, onMessage, onToggle }) {
  const [form, setForm] = useState({ name: '', code: '' })
  const [seeding, setSeeding] = useState(false)

  async function seedMoe() {
    setSeeding(true)
    const res = await apiWrite('/api/learning-areas/seed-moe/', {})
    setSeeding(false)
    if (res.ok) {
      onMessage(
        `MoE set loaded — ${res.data.created} added, ${res.data.updated} updated. ` +
        'Untick anything your school does not offer.',
      )
      onChanged()
    } else {
      onMessage(res.data?.detail || 'Could not load the MoE set.')
    }
  }

  async function add(e) {
    e.preventDefault()
    const name = form.name.trim()
    if (!name) {
      onMessage('Give the learning area a name.')
      return
    }
    const code = form.code.trim().toUpperCase() ||
      name.replace(/[^A-Za-z]/g, '').slice(0, 6).toUpperCase()
    const res = await apiWrite('/api/learning-areas/', { name, code, grades: [] })
    if (res.ok) {
      setForm({ name: '', code: '' })
      onChanged()
    } else {
      onMessage(JSON.stringify(res.data) || 'Could not add the learning area.')
    }
  }

  return (
    <div className="card">
      <div className="page-header" style={{ marginBottom: 0 }}>
        <h3 style={{ margin: 0 }}>Learning areas (subjects)</h3>
        <button onClick={seedMoe} disabled={seeding}>
          {seeding ? 'Loading…' : 'Load the MoE set'}
        </button>
      </div>
      <p className="muted">
        The KICD/MoE curriculum per level, one click — then tick the grades where
        each is taught. These choices feed teaching assignments, assessments,
        teacher subjects, schemes of work and the timetable.
      </p>
      <form onSubmit={add}
        style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.7rem' }}>
        <input placeholder="New learning area e.g. Agriculture" value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          style={{ padding: '0.4rem', minWidth: '14rem' }} />
        <input placeholder="Code (optional)" value={form.code}
          onChange={(e) => setForm({ ...form, code: e.target.value })}
          style={{ padding: '0.4rem', width: '8rem' }} />
        <button className="primary" type="submit">Add</button>
      </form>
      {areas.length === 0 && (
        <p className="muted">None yet — load the MoE set or add your own.</p>
      )}
      <table>
        <tbody>
          {areas.map((area) => (
            <tr key={area.id}>
              <td style={{ whiteSpace: 'nowrap' }}>
                <b>{area.name}</b>
                <div className="muted">{area.code}</div>
              </td>
              <td>
                {ALL_GRADES.map((g) => (
                  <button
                    key={g}
                    type="button"
                    className={`grade-chip${area.grades.includes(g) ? ' on' : ''}`}
                    style={{ margin: '0.12rem 0.18rem' }}
                    onClick={() => onToggle(area, g)}
                  >
                    {gradeLabel(g)}
                  </button>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function SchoolStructure({ grade }) {
  const [structure, setStructure] = useState(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [selected, setSelected] = useState(null) // {grade, label}
  const [refresh, setRefresh] = useState(0)
  const reload = () => setRefresh((n) => n + 1)

  // Reload whenever we come back to the overview, so a class teacher assigned
  // inside a grade shows up in the list straight away.
  useEffect(() => {
    if (selected) return
    apiGet('/api/school/structure/').then(setStructure).catch((e) => setError(e.message))
  }, [selected, refresh])

  // The learning-areas register, shared by the per-grade column and the card.
  const [areas, setAreas] = useState([])
  useEffect(() => {
    if (selected) return
    apiGet('/api/learning-areas/?page_size=200')
      .then((d) => setAreas(d.results || d))
      .catch(() => setAreas([]))
  }, [selected, refresh])

  async function toggleAreaGrade(area, g) {
    const grades = area.grades.includes(g)
      ? area.grades.filter((x) => x !== g)
      : [...area.grades, g].sort((a, b) => a - b)
    const res = await apiWrite(
      `/api/learning-areas/${area.id}/`, { grades }, { method: 'PATCH' },
    )
    if (!res.ok) setMessage('Could not update that learning area.')
    reload()
  }

  // A grade picked from the sidebar opens that class directly.
  useEffect(() => {
    setSelected(
      grade === null || grade === undefined
        ? null
        : { grade, label: gradeLabel(grade) },
    )
  }, [grade])

  if (error) return <div className="error">{error}</div>
  if (!structure) return <p className="muted">Loading school structure…</p>
  if (selected) {
    return (
      <GradeDetail
        grade={selected.grade}
        label={selected.label}
        onBack={() => setSelected(null)}
      />
    )
  }

  return (
    <div>
      {message && <p className="error">{message}</p>}
      {structure.categories.map((cat) => (
        <div className="card" key={cat.name}>
          <h3>{cat.name}</h3>
          <table>
            <thead>
              <tr>
                <th>Grade</th><th>Learners</th><th>Male</th><th>Female</th>
                <th>Streams</th><th>Learning areas</th><th>Class teacher(s)</th><th></th>
              </tr>
            </thead>
            <tbody>
              {cat.grades.map((g) => (
                <tr key={g.grade}>
                  <td>{g.label}</td>
                  <td>{g.total}</td>
                  <td>{g.male}</td>
                  <td>{g.female}</td>
                  <td>
                    <StreamsCell grade={g.grade} classes={g.classes}
                      onChanged={reload} onMessage={setMessage} />
                  </td>
                  <td>
                    <GradeAreasCell grade={g.grade} areas={areas}
                      onToggle={toggleAreaGrade} />
                  </td>
                  <td className="muted">
                    {g.classes.length === 0
                      ? '—'
                      : g.classes
                          .map((c) => `${c.stream || ''} ${c.class_teacher || 'unassigned'}`.trim())
                          .join(', ')}
                  </td>
                  <td>
                    <button onClick={() => setSelected({ grade: g.grade, label: g.label })}>
                      Open
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}

      <LearningAreasCard
        areas={areas}
        onChanged={reload}
        onMessage={setMessage}
        onToggle={toggleAreaGrade}
      />
    </div>
  )
}
