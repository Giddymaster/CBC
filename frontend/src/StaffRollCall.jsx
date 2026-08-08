import { useCallback, useEffect, useState } from 'react'
import { apiGet, apiWrite } from './api.js'
import { todayLocal } from './format.js'

const OPTIONS = [
  { value: 'P', label: 'Present' },
  { value: 'A', label: 'Absent' },
  { value: 'L', label: 'On leave' },
]

const MARK_BADGE = { P: 'online', A: 'offline', L: 'queued' }

function shiftDay(iso, delta) {
  const d = new Date(`${iso}T12:00:00`)
  d.setDate(d.getDate() + delta)
  return d.toISOString().slice(0, 10)
}

function dayHeading(iso) {
  const d = new Date(`${iso}T12:00:00`)
  return d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })
}

/** Staff × day for the last few school weeks — absence as a pattern, not a
 * single morning's snapshot. */
function RollCallHistory() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    apiGet('/api/staff/roll-call/history/?days=14')
      .then(setData)
      .catch((e) => setError(e.message))
  }, [])

  if (error) return <div className="error">{error}</div>
  if (!data) return <p className="muted">Loading history…</p>

  return (
    <>
      <p className="muted">
        The last {data.days.length} school days. P present · A absent · L on leave.
      </p>
      <table>
        <thead>
          <tr>
            <th>Name</th>
            {data.days.map((d) => (
              <th key={d} title={d}>{dayHeading(d).split(' ').slice(1).join(' ')}</th>
            ))}
            <th>P</th><th>A</th><th>L</th>
          </tr>
        </thead>
        <tbody>
          {data.staff.map((s) => (
            <tr key={s.teacher}>
              <td style={{ whiteSpace: 'nowrap' }}>
                <b>{s.name}</b>
                <div className="muted">{s.rank}</div>
              </td>
              {data.days.map((d) => (
                <td key={d}>
                  {s.marks[d]
                    ? <span className={`badge ${MARK_BADGE[s.marks[d]]}`}>{s.marks[d]}</span>
                    : <span className="muted">·</span>}
                </td>
              ))}
              <td><b>{s.totals.present}</b></td>
              <td>{s.totals.absent > 0
                ? <b style={{ color: '#c53030' }}>{s.totals.absent}</b> : 0}</td>
              <td>{s.totals.on_leave}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}

/** Staff register — the same shape as the learner one. */
export default function StaffRollCall() {
  const [date, setDate] = useState(todayLocal())
  const [view, setView] = useState('DAY') // DAY | HISTORY
  const [data, setData] = useState(null)
  const [marks, setMarks] = useState({})
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    apiGet(`/api/staff/roll-call/?date=${date}`)
      .then((d) => {
        setData(d)
        setMarks(Object.fromEntries(d.staff.map((s) => [s.teacher, s.status])))
        setError('')
      })
      .catch((e) => setError(e.message))
  }, [date])
  useEffect(load, [load])

  async function save() {
    setBusy(true)
    const records = Object.entries(marks)
      .filter(([, status]) => status)
      .map(([teacher, status]) => ({ teacher: Number(teacher), status }))
    const res = await apiWrite('/api/staff/roll-call/', { date, records })
    setBusy(false)
    setMessage(
      res.queued
        ? 'Offline — the register is queued and will sync when the connection returns.'
        : res.ok
          ? `Saved ${res.data.saved.length} staff.`
          : 'Could not save the register.',
    )
    if (res.ok) load()
  }

  function markAll(value) {
    setMarks(Object.fromEntries((data?.staff || []).map((s) => [s.teacher, value])))
  }

  if (error) return <div className="error">{error}</div>
  if (!data) return <p className="muted">Loading…</p>

  const counted = (value) => Object.values(marks).filter((m) => m === value).length

  return (
    <div className="card">
      <div className="page-header" style={{ marginBottom: '0.4rem' }}>
        <h3 style={{ margin: 0 }}>
          Staff register{view === 'DAY' && ` — ${dayHeading(date)}`}
        </h3>
        <span style={{ display: 'flex', gap: '0.4rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <button
            className={`grade-chip${view === 'HISTORY' ? ' on' : ''}`}
            onClick={() => setView(view === 'HISTORY' ? 'DAY' : 'HISTORY')}
          >
            {view === 'HISTORY' ? 'Back to the day' : 'History'}
          </button>
          {view === 'DAY' && (
            <>
              <button onClick={() => setDate(shiftDay(date, -1))} title="Previous day">←</button>
              <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
              <button onClick={() => setDate(shiftDay(date, 1))}
                disabled={date >= todayLocal()} title="Next day">→</button>
              {date !== todayLocal() && (
                <button onClick={() => setDate(todayLocal())}>Today</button>
              )}
            </>
          )}
        </span>
      </div>

      {view === 'HISTORY' && <RollCallHistory />}
      {view === 'HISTORY' ? null : (
      <>
      <p className="muted">
        {counted('P')} present · {counted('A')} absent · {counted('L')} on leave ·{' '}
        {data.staff.length - Object.values(marks).filter(Boolean).length} not marked
        {' · '}
        <button onClick={() => markAll('P')} style={{ padding: '0.15rem 0.5rem' }}>
          Mark all present
        </button>
      </p>

      <table>
        <thead>
          <tr><th>Name</th><th>Rank</th><th>TSC / Payroll</th><th>Today</th></tr>
        </thead>
        <tbody>
          {data.staff.map((s) => (
            <tr key={s.teacher}>
              <td>{s.name}</td>
              <td className="muted">{s.rank}</td>
              <td className="muted">{s.tsc_number}</td>
              <td>
                <span style={{ display: 'flex', gap: '0.3rem' }}>
                  {OPTIONS.map((o) => (
                    <button
                      key={o.value}
                      className={marks[s.teacher] === o.value ? 'roll-btn on' : 'roll-btn'}
                      onClick={() =>
                        setMarks({ ...marks, [s.teacher]: marks[s.teacher] === o.value ? null : o.value })
                      }
                    >
                      {o.label}
                    </button>
                  ))}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <p>
        <button className="primary" onClick={save} disabled={busy}>
          {busy ? 'Saving…' : 'Save register'}
        </button>
        {message && <span className="muted"> {message}</span>}
      </p>
      </>
      )}
    </div>
  )
}
