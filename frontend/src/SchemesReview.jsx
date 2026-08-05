import { useCallback, useEffect, useState } from 'react'
import { apiGet, apiWrite } from './api.js'
import { gradeLabel, gradeParam } from './format.js'
import { SchemeWeeks, StatusBadge } from './Schemes.jsx'

// Admin/head view: review uploaded and AI-generated schemes of work.
export default function SchemesReview({ grade }) {
  const [schemes, setSchemes] = useState([])
  const [filter, setFilter] = useState('PENDING')
  const [openId, setOpenId] = useState(null)
  const [comments, setComments] = useState({})
  const [message, setMessage] = useState('')

  const load = useCallback(() => {
    const params = []
    if (filter !== 'ALL') params.push(`status=${filter}`)
    const g = gradeParam(grade)
    if (g) params.push(g)
    apiGet(`/api/schemes-of-work/${params.length ? `?${params.join('&')}` : ''}`)
      .then((d) => setSchemes(d.results || d))
  }, [filter, grade])
  useEffect(load, [load])

  async function review(scheme, decision) {
    const result = await apiWrite(`/api/schemes-of-work/${scheme.id}/review/`, {
      decision,
      comment: comments[scheme.id] || '',
    })
    setMessage(result.ok
      ? `Scheme ${decision === 'approve' ? 'approved' : 'rejected'}.`
      : 'Review failed — are you signed in as the admin?')
    load()
  }

  return (
    <div className="card">
      <p>
        <select value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="PENDING">Pending review</option>
          <option value="APPROVED">Approved</option>
          <option value="REJECTED">Rejected</option>
          <option value="ALL">All</option>
        </select>{' '}
        <span className="muted">Schemes of work submitted by teachers</span>
      </p>
      {message && <p className="muted">{message}</p>}
      {schemes.length === 0 && <p className="muted">Nothing in this queue.</p>}
      {schemes.map((s) => (
        <div key={s.id} className="card">
          <p>
            <b>{s.learning_area_name}</b> — {gradeLabel(s.grade)}, T{s.term} {s.year} —{' '}
            {s.teacher_name || 'Unknown teacher'}{' '}
            <StatusBadge status={s.status} />{' '}
            <span className="muted">
              {s.source === 'GENERATED' ? 'AI generated' :
                s.source === 'UPLOADED' ? 'Uploaded document' : 'Manual entry'}
            </span>
          </p>
          <p>
            {s.document && (
              <a href={s.document} target="_blank" rel="noreferrer">Open uploaded document</a>
            )}{' '}
            {s.content?.weeks?.length > 0 && (
              <button onClick={() => setOpenId(openId === s.id ? null : s.id)}>
                {openId === s.id ? 'Hide content' : 'View content'}
              </button>
            )}{' '}
          </p>
          {s.status === 'PENDING' && (
            <p style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              <input
                type="text"
                placeholder="Comment for the teacher (optional for approval)"
                style={{ flex: 1, minWidth: '16rem', padding: '0.4rem' }}
                value={comments[s.id] || ''}
                onChange={(e) => setComments({ ...comments, [s.id]: e.target.value })}
              />
              <button className="primary" onClick={() => review(s, 'approve')}>Approve</button>
              <button onClick={() => review(s, 'reject')}>Reject</button>
            </p>
          )}
          {s.review_comment && <p className="muted">Review note: {s.review_comment}</p>}
          {openId === s.id && <SchemeWeeks content={s.content} />}
        </div>
      ))}
    </div>
  )
}
