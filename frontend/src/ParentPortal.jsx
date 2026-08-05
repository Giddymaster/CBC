import { useEffect, useState } from 'react'
import { ParentThreads } from './ParentMessages.jsx'
import { apiGet } from './api.js'
import { gradeLabel } from './format.js'

function ChildCard({ child }) {
  const report = child.report_card
  const learner = report.learner
  return (
    <div className="card">
      <h3>
        {learner.name} — {gradeLabel(learner.grade)} {learner.stream}
      </h3>
      <p>
        Fee balance: <b>KES {child.fees.total_balance}</b>{' '}
        {child.fees.invoices.map((inv) => (
          <span key={inv.id} className={`badge ${inv.status === 'PAID' ? 'online' : 'queued'}`}>
            {inv.status}
          </span>
        ))}
      </p>
      {Object.keys(report.learning_areas).length > 0 ? (
        <table>
          <thead>
            <tr><th>Learning area</th><th>Assessment</th><th>Marks</th><th>Level</th></tr>
          </thead>
          <tbody>
            {Object.entries(report.learning_areas).flatMap(([area, kinds]) =>
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
      ) : (
        <p className="muted">No assessment records yet this year.</p>
      )}
    </div>
  )
}

export default function ParentPortal() {
  const [summary, setSummary] = useState(null)
  const [error, setError] = useState('')
  const [tab, setTab] = useState('My Children')

  useEffect(() => {
    apiGet('/api/parent/summary/').then(setSummary).catch((e) => setError(e.message))
  }, [])

  if (error) return <div className="error">{error}</div>
  if (!summary) return <p className="muted">Loading…</p>

  return (
    <div>
      <p className="muted">
        {summary.guardian.name} — {summary.school} — {summary.year}
      </p>
      <nav className="tabs">
        {['My Children', 'Messages'].map((name) => (
          <button key={name} className={tab === name ? 'active' : ''} onClick={() => setTab(name)}>
            {name}
          </button>
        ))}
      </nav>

      {tab === 'Messages' && <ParentThreads />}

      {tab === 'My Children' && <>
      {summary.children.map((child) => (
        <ChildCard key={child.report_card.learner.id} child={child} />
      ))}
      <div className="card">
        <h3>Announcements</h3>
        {summary.announcements.length === 0 && <p className="muted">Nothing yet.</p>}
        {summary.announcements.map((a) => (
          <p key={a.id}>
            <b>{a.title}</b> <span className="muted">({a.date})</span>
            <br />
            {a.body}{' '}
            {a.meeting_link && (
              <a href={a.meeting_link} target="_blank" rel="noreferrer">Join meeting</a>
            )}
          </p>
        ))}
      </div>
      </>}
    </div>
  )
}
