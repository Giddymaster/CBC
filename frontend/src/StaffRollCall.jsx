import { useCallback, useEffect, useState } from 'react'
import { apiGet, apiWrite } from './api.js'
import { todayLocal } from './format.js'

const OPTIONS = [
  { value: 'P', label: 'Present' },
  { value: 'A', label: 'Absent' },
  { value: 'L', label: 'On leave' },
]

/** Staff register — the same shape as the learner one. */
export default function StaffRollCall() {
  const [date, setDate] = useState(todayLocal())
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
        <h3 style={{ margin: 0 }}>Staff register</h3>
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
      </div>
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
    </div>
  )
}
