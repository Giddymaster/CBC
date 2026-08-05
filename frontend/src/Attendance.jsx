import { useEffect, useState } from 'react'
import { apiGet, apiWrite } from './api.js'
import { gradeParam, todayLocal } from './format.js'

const STATUS_LABEL = { P: 'Present', A: 'Absent', L: 'Late', E: 'Excused' }
const STATUS_BADGE = { P: 'online', A: 'offline', L: 'queued', E: 'queued' }

export default function Attendance({ onQueueChange, grade }) {
  const [learners, setLearners] = useState([])
  const [statuses, setStatuses] = useState({})
  const [marked, setMarked] = useState({})
  const [date, setDate] = useState(todayLocal)
  const [message, setMessage] = useState('')

  useEffect(() => {
    const q = gradeParam(grade)
    apiGet(`/api/learners/?page_size=200${q ? `&${q}` : ''}`).then((data) => {
      const list = data.results || data
      setLearners(list)
      setStatuses(Object.fromEntries(list.map((l) => [l.id, 'P'])))
    })
  }, [grade])

  // Show what is already recorded for the chosen day, so the admin can see a
  // grade's register rather than only entering a new one.
  useEffect(() => {
    apiGet(`/api/attendance/?date=${date}&page_size=500`)
      .then((data) => {
        const rows = data.results || data
        setMarked(Object.fromEntries(rows.map((r) => [r.learner, r.status])))
      })
      .catch(() => setMarked({}))
  }, [date, grade])

  async function submit() {
    const records = learners.map((l) => ({ learner: l.id, status: statuses[l.id] }))
    const result = await apiWrite('/api/attendance/bulk/', { date, records })
    if (result.queued) {
      setMessage('Offline — register queued locally, will sync when connection returns.')
    } else if (result.ok) {
      setMessage(`Synced: ${result.data.created} new, ${result.data.updated} updated.`)
      setMarked((prev) => ({ ...prev, ...Object.fromEntries(records.map((r) => [r.learner, r.status])) }))
    } else {
      setMessage('Rejected by server — check the register.')
    }
    onQueueChange()
  }

  const tally = learners.reduce(
    (acc, l) => {
      const s = marked[l.id]
      if (s) acc[s] = (acc[s] || 0) + 1
      else acc.unmarked += 1
      return acc
    },
    { unmarked: 0 },
  )

  return (
    <div className="card">
      <p>
        Register for <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
      </p>
      <p className="muted">
        {learners.length} learners · recorded: {tally.P || 0} present, {tally.A || 0} absent,{' '}
        {tally.L || 0} late, {tally.E || 0} excused, {tally.unmarked} not marked
      </p>
      <table>
        <thead>
          <tr><th>Adm No</th><th>Learner</th><th>Recorded</th><th>Mark</th></tr>
        </thead>
        <tbody>
          {learners.map((l) => (
            <tr key={l.id}>
              <td>{l.admission_number}</td>
              <td>{l.full_name}</td>
              <td>
                {marked[l.id] ? (
                  <span className={`badge ${STATUS_BADGE[marked[l.id]]}`}>
                    {STATUS_LABEL[marked[l.id]]}
                  </span>
                ) : (
                  <span className="muted">Not marked</span>
                )}
              </td>
              <td>
                <select
                  value={statuses[l.id] || 'P'}
                  onChange={(e) => setStatuses({ ...statuses, [l.id]: e.target.value })}
                >
                  <option value="P">Present</option>
                  <option value="A">Absent</option>
                  <option value="L">Late</option>
                  <option value="E">Excused</option>
                </select>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p>
        <button className="primary" onClick={submit} disabled={!learners.length}>
          Submit register
        </button>
      </p>
      {message && <div className="muted">{message}</div>}
    </div>
  )
}
