import { useCallback, useEffect, useState } from 'react'
import { apiGet, apiWrite } from './api.js'
import { gradeLabel } from './format.js'

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
          <th>Period</th>
          {Object.values(DAY_NAMES).map((d) => <th key={d}>{d}</th>)}
        </tr>
      </thead>
      <tbody>
        {periods.map((p) => (
          <tr key={p}>
            <td>P{p}<div className="muted">{times[p]}</div></td>
            {Object.keys(DAY_NAMES).map((day) => {
              const l = grid[p]?.[day]
              return (
                <td key={day}>
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

function GradeDetail({ grade, label, onBack }) {
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState('')
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

export default function SchoolStructure({ grade }) {
  const [structure, setStructure] = useState(null)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState(null) // {grade, label}

  // Reload whenever we come back to the overview, so a class teacher assigned
  // inside a grade shows up in the list straight away.
  useEffect(() => {
    if (selected) return
    apiGet('/api/school/structure/').then(setStructure).catch((e) => setError(e.message))
  }, [selected])

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
      {structure.categories.map((cat) => (
        <div className="card" key={cat.name}>
          <h3>{cat.name}</h3>
          <table>
            <thead>
              <tr><th>Grade</th><th>Learners</th><th>Male</th><th>Female</th><th>Class teacher(s)</th><th></th></tr>
            </thead>
            <tbody>
              {cat.grades.map((g) => (
                <tr key={g.grade}>
                  <td>{g.label}</td>
                  <td>{g.total}</td>
                  <td>{g.male}</td>
                  <td>{g.female}</td>
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
    </div>
  )
}
