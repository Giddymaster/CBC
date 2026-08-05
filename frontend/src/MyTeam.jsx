import { useCallback, useEffect, useState } from 'react'
import { apiGet, apiWrite } from './api.js'
import { Avatar } from './StaffPortal.jsx'

const TASK_BADGE = { OPEN: 'queued', DOING: 'queued', DONE: 'online' }
const REPORT_BADGE = {
  DRAFT: 'queued', SUBMITTED: 'queued', APPROVED: 'online', RETURNED: 'offline',
}

function TeamMember({ userId, onBack }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [task, setTask] = useState({ title: '', description: '', due_date: '', priority: 'NORMAL' })
  const [note, setNote] = useState('')
  const [comments, setComments] = useState({})

  const load = useCallback(() => {
    apiGet(`/api/my-team/${userId}/`).then(setData).catch((e) => setError(e.message))
  }, [userId])
  useEffect(load, [load])

  if (error) return <div className="error">{error}</div>
  if (!data) return <p className="muted">Loading…</p>

  async function assignTask(e) {
    e.preventDefault()
    if (!task.title.trim()) {
      setMessage('Give the task a title.')
      return
    }
    const body = { ...task, assigned_to: userId }
    if (!body.due_date) delete body.due_date
    const res = await apiWrite('/api/staff-tasks/', body)
    setMessage(res.ok ? 'Work assigned.' : `Failed: ${JSON.stringify(res.data)}`)
    if (res.ok) {
      setTask({ title: '', description: '', due_date: '', priority: 'NORMAL' })
      load()
    }
  }

  async function sendNote(e) {
    e.preventDefault()
    if (!note.trim()) return
    const res = await apiWrite('/api/staff-messages/', { recipient: userId, body: note })
    setMessage(res.ok ? 'Message sent.' : 'Could not send message.')
    if (res.ok) {
      setNote('')
      load()
    }
  }

  async function reviewReport(report, decision) {
    const res = await apiWrite(`/api/staff-reports/${report.id}/review/`, {
      decision,
      comment: comments[report.id] || '',
    })
    setMessage(
      res.ok
        ? `Report ${decision === 'approve' ? 'approved' : 'returned'}.`
        : res.data?.detail || 'Could not review.',
    )
    load()
  }

  const p = data.person
  return (
    <div>
      <p>
        <button onClick={onBack}>← My team</button>
      </p>

      <div className="card profile-card">
        <div className="profile-head">
          <Avatar person={p} size="md" />
          <div className="profile-headline">
            <h3>{p.name}</h3>
            <p className="profile-title">{p.title}</p>
            <p className="muted">
              {data.category}
              {p.phone && <> · <a href={`tel:${p.phone}`}>{p.phone}</a></>}
            </p>
          </div>
        </div>
        {data.responsibilities.length > 0 && (
          <div className="profile-grid">
            <div className="profile-field">
              <span className="profile-label">Responsibilities</span>
              <span className="profile-value">{data.responsibilities.join(' · ')}</span>
            </div>
          </div>
        )}
      </div>
      {message && <p className="muted">{message}</p>}

      <div className="card">
        <h3>Assign work</h3>
        <form onSubmit={assignTask} style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <input placeholder="What needs doing" value={task.title}
            onChange={(e) => setTask({ ...task, title: e.target.value })}
            style={{ padding: '0.4rem', minWidth: '15rem' }} />
          <input placeholder="Details (optional)" value={task.description}
            onChange={(e) => setTask({ ...task, description: e.target.value })}
            style={{ padding: '0.4rem', minWidth: '13rem' }} />
          <input type="date" value={task.due_date}
            onChange={(e) => setTask({ ...task, due_date: e.target.value })} />
          <select value={task.priority} onChange={(e) => setTask({ ...task, priority: e.target.value })}>
            <option value="NORMAL">Normal</option>
            <option value="HIGH">High</option>
          </select>
          <button className="primary" type="submit">Assign</button>
        </form>

        {data.tasks.length > 0 && (
          <table>
            <thead>
              <tr><th>Task</th><th>Due</th><th>Priority</th><th>Status</th></tr>
            </thead>
            <tbody>
              {data.tasks.map((t) => (
                <tr key={t.id}>
                  <td>{t.title}{t.description && <div className="muted">{t.description}</div>}</td>
                  <td className="muted">{t.due_date || '—'}</td>
                  <td>{t.priority === 'HIGH' ? <span className="badge offline">High</span> : 'Normal'}</td>
                  <td><span className={`badge ${TASK_BADGE[t.status]}`}>{t.status_label}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h3>Their reports</h3>
        {data.reports.length === 0 && <p className="muted">No reports filed yet.</p>}
        {data.reports.map((r) => (
          <div key={r.id} style={{ borderBottom: '1px solid #e2e8f0', paddingBottom: '0.6rem', marginBottom: '0.6rem' }}>
            <p>
              <b>{r.title}</b>{' '}
              <span className={`badge ${REPORT_BADGE[r.status]}`}>{r.status}</span>{' '}
              <span className="muted">{r.period}</span>
            </p>
            {r.body && <p>{r.body}</p>}
            {r.status === 'SUBMITTED' && (
              <p style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                <input placeholder="Comment" style={{ flex: 1, minWidth: '12rem', padding: '0.4rem' }}
                  value={comments[r.id] || ''}
                  onChange={(e) => setComments({ ...comments, [r.id]: e.target.value })} />
                <button className="primary" onClick={() => reviewReport(r, 'approve')}>Approve</button>
                <button onClick={() => reviewReport(r, 'return')}>Return</button>
              </p>
            )}
            {r.review_comment && <p className="muted">Feedback: {r.review_comment}</p>}
          </div>
        ))}
      </div>

      <div className="card">
        <h3>Messages</h3>
        {data.messages.length === 0 && <p className="muted">No messages yet.</p>}
        {data.messages.map((m) => (
          <p key={m.id}>
            <b>{m.sender_name}</b>{' '}
            <span className="muted">{new Date(m.created_at).toLocaleString()}</span>
            <br />
            {m.body}
          </p>
        ))}
        <form onSubmit={sendNote} style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <input placeholder={`Message ${p.name.split(' ')[0]}…`} value={note}
            onChange={(e) => setNote(e.target.value)}
            style={{ flex: 1, minWidth: '16rem', padding: '0.4rem' }} />
          <button className="primary" type="submit">Send</button>
        </form>
      </div>
    </div>
  )
}

export default function MyTeam() {
  const [team, setTeam] = useState(null)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState(null)

  const load = useCallback(() => {
    apiGet('/api/my-team/').then(setTeam).catch((e) => setError(e.message))
  }, [])
  useEffect(load, [load])

  if (error) return <div className="error">{error}</div>
  if (!team) return <p className="muted">Loading team…</p>
  if (selected) {
    return <TeamMember userId={selected} onBack={() => { setSelected(null); load() }} />
  }
  if (team.total === 0) {
    return <p className="muted">Nobody reports to you.</p>
  }

  return (
    <div>
      <p className="muted">
        {team.total} staff · view scope: <b>{team.scope}</b>
      </p>
      {team.groups.map((group) => (
        <div className="card" key={group.category}>
          <h3>{group.category} ({group.staff.length})</h3>
          <table>
            <thead>
              <tr>
                <th>Name</th><th>Position</th><th>Line</th>
                <th>Open work</th><th>Reports pending</th><th></th>
              </tr>
            </thead>
            <tbody>
              {group.staff.map((p) => (
                <tr key={p.id}>
                  <td>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <Avatar person={p} size="sm" />
                      {p.name}
                    </span>
                  </td>
                  <td>{p.title}</td>
                  <td className="muted">{p.direct ? 'Direct report' : 'Below my line'}</td>
                  <td>{p.open_tasks || <span className="muted">—</span>}</td>
                  <td>
                    {p.pending_reports
                      ? <span className="badge queued">{p.pending_reports} to review</span>
                      : <span className="muted">—</span>}
                  </td>
                  <td><button onClick={() => setSelected(p.id)}>Open</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  )
}
