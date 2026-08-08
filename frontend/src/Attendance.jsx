import { useCallback, useEffect, useState } from 'react'
import { apiGet, apiWrite } from './api.js'
import { ALL_GRADES, gradeLabel, gradeParam, todayLocal } from './format.js'

const STATUS_LABEL = { P: 'Present', A: 'Absent', H: 'Half day', L: 'Late', E: 'Excused' }

/** Every learner, not just the first page. */
async function fetchAllLearners(query) {
  const rows = []
  let url = `/api/learners/?page_size=500${query ? `&${query}` : ''}`
  while (url) {
    const d = await apiGet(url)
    rows.push(...(d.results || d))
    url = d.next ? d.next.slice(d.next.indexOf('/api/')) : null
  }
  return rows
}

/** The day's register: the class teacher marks it. Each learner's control is
 * pre-set to whatever is already recorded, so re-opening the day corrects it
 * rather than starting over. */
function Register({ onQueueChange, grade }) {
  const [learners, setLearners] = useState([])
  const [statuses, setStatuses] = useState({})
  const [date, setDate] = useState(todayLocal)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    fetchAllLearners(gradeParam(grade)).then(setLearners).catch(() => setLearners([]))
  }, [grade])

  useEffect(() => {
    apiGet(`/api/attendance/?date=${date}&page_size=500`)
      .then((data) => {
        const rows = data.results || data
        setStatuses(Object.fromEntries(rows.map((r) => [r.learner, r.status])))
      })
      .catch(() => setStatuses({}))
  }, [date, grade])

  async function submit() {
    setBusy(true)
    const records = learners.map((l) => ({ learner: l.id, status: statuses[l.id] || 'P' }))
    const result = await apiWrite('/api/attendance/bulk/', { date, records })
    setBusy(false)
    if (result.queued) {
      setMessage('Offline — register queued locally, will sync when connection returns.')
    } else if (result.ok) {
      setMessage(`Saved: ${result.data.created} new, ${result.data.updated} corrected.`)
    } else {
      setMessage(result.data?.detail || 'Rejected by server — check the register.')
    }
    onQueueChange?.()
  }

  const tally = learners.reduce((acc, l) => {
    const s = statuses[l.id]
    if (s) acc[s] = (acc[s] || 0) + 1
    else acc.unmarked += 1
    return acc
  }, { unmarked: 0 })

  return (
    <>
      <p style={{ display: 'flex', gap: '0.6rem', alignItems: 'center', flexWrap: 'wrap' }}>
        Register for <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        <button className="grade-chip"
          onClick={() => setStatuses(Object.fromEntries(learners.map((l) => [l.id, 'P'])))}>
          Mark all present
        </button>
      </p>
      <p className="muted">
        {learners.length} learners · {tally.P || 0} present · {tally.A || 0} absent ·{' '}
        {tally.H || 0} half day · {tally.L || 0} late · {tally.E || 0} excused ·{' '}
        {tally.unmarked} not marked
      </p>
      <table>
        <thead>
          <tr><th>Adm No</th><th>Learner</th><th>Mark</th></tr>
        </thead>
        <tbody>
          {learners.map((l) => (
            <tr key={l.id}>
              <td>{l.admission_number}</td>
              <td>{l.full_name}</td>
              <td>
                <span style={{ display: 'flex', gap: '0.3rem', flexWrap: 'wrap' }}>
                  {Object.entries(STATUS_LABEL).map(([value, label]) => (
                    <button
                      key={value}
                      className={statuses[l.id] === value ? 'roll-btn on' : 'roll-btn'}
                      onClick={() => setStatuses({ ...statuses, [l.id]: value })}
                    >
                      {label}
                    </button>
                  ))}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p>
        <button className="primary" onClick={submit} disabled={busy || !learners.length}>
          {busy ? 'Saving…' : 'Save register'}
        </button>
        {message && <span className="muted"> {message}</span>}
      </p>
    </>
  )
}

function MarkCell({ status }) {
  if (!status) return <td className="att-cell" />
  if (status === 'P') return <td className="att-cell att-p" title="Present">✓</td>
  if (status === 'A') return <td className="att-cell att-a" title="Absent">✗</td>
  if (status === 'H') return <td className="att-cell att-h" title="Half day">H</td>
  return (
    <td className="att-cell att-o" title={STATUS_LABEL[status] || status}>
      {status}
    </td>
  )
}

/** The month as a wall calendar: learners down, school days across, weeks in
 * alternating shades. Read-only — this is how the office and the head teacher
 * see attendance. */
function MonthView({ grade: fixedGrade }) {
  const now = todayLocal()
  const [month, setMonth] = useState(now.slice(0, 7)) // YYYY-MM
  const [grade, setGrade] = useState(fixedGrade ?? 4)
  const [data, setData] = useState(null)

  useEffect(() => {
    if (fixedGrade !== null && fixedGrade !== undefined) setGrade(fixedGrade)
  }, [fixedGrade])

  const load = useCallback(() => {
    const [y, m] = month.split('-')
    apiGet(`/api/attendance/month/?year=${y}&month=${Number(m)}&grade=${grade}`)
      .then(setData)
      .catch(() => setData(null))
  }, [month, grade])
  useEffect(load, [load])

  const shift = (delta) => {
    const [y, m] = month.split('-').map(Number)
    const d = new Date(y, m - 1 + delta, 1)
    setMonth(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`)
  }

  // Alternating background per ISO week.
  const weekClass = (() => {
    const weeks = [...new Set((data?.days || []).map((d) => d.week))]
    return (w) => (weeks.indexOf(w) % 2 ? 'att-week-b' : 'att-week-a')
  })()

  return (
    <>
      <p style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
        {(fixedGrade === null || fixedGrade === undefined) && (
          <select value={grade} onChange={(e) => setGrade(Number(e.target.value))}>
            {ALL_GRADES.map((g) => (
              <option key={g} value={g}>{gradeLabel(g)}</option>
            ))}
          </select>
        )}
        <button onClick={() => shift(-1)} title="Previous month">←</button>
        <input type="month" value={month} onChange={(e) => setMonth(e.target.value)} />
        <button onClick={() => shift(1)} title="Next month">→</button>
        <span className="muted">
          ✓ present · ✗ absent · H half day · L late · E excused
        </span>
      </p>
      {data && data.learners.length === 0 && (
        <p className="muted">No learners in {gradeLabel(grade)}.</p>
      )}
      {data && data.learners.length > 0 && (
        <table className="att-month">
          <thead>
            <tr>
              <th>Adm No</th>
              <th>Learner</th>
              {data.days.map((d) => (
                <th key={d.date} className={weekClass(d.week)} title={d.date}>
                  {Number(d.date.slice(8, 10))}
                  <div className="muted">{'MTWTF'[d.dow]}</div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.learners.map((l) => (
              <tr key={l.id}>
                <td className="muted">{l.admission_number}</td>
                <td style={{ whiteSpace: 'nowrap' }}>{l.name}</td>
                {data.days.map((d) => (
                  <MarkCell key={d.date} status={l.marks[d.date]} />
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  )
}

/**
 * canMark: the class teacher's power. The admin and the head teacher open this
 * page read-only — marking is enforced server-side too.
 */
export default function Attendance({ onQueueChange, grade, canMark = false }) {
  const [view, setView] = useState(canMark ? 'REGISTER' : 'MONTH')

  return (
    <div className="card">
      {canMark && (
        <p style={{ display: 'flex', gap: '0.4rem' }}>
          <button className={`grade-chip${view === 'REGISTER' ? ' on' : ''}`}
            onClick={() => setView('REGISTER')}>Mark the day</button>
          <button className={`grade-chip${view === 'MONTH' ? ' on' : ''}`}
            onClick={() => setView('MONTH')}>Month view</button>
        </p>
      )}
      {!canMark && (
        <p className="muted">
          The register is marked by each class teacher; this is the month's
          record.
        </p>
      )}
      {view === 'REGISTER' && canMark && (
        <Register onQueueChange={onQueueChange} grade={grade} />
      )}
      {view === 'MONTH' && <MonthView grade={grade ?? null} />}
    </div>
  )
}
