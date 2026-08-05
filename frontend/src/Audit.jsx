import { useCallback, useEffect, useState } from 'react'
import { apiGet } from './api.js'

const SERIOUS = new Set([
  'SCORE_CHANGED', 'LEARNER_DEACTIVATED', 'PASSWORD_RESET',
  'PROMOTION_APPLIED', 'PROMOTION_REVERSED', 'RIGHTS_GRANTED',
])

/** What a `detail` blob means, in words. */
function Detail({ action, detail }) {
  if (!detail || !Object.keys(detail).length) return null
  if (action === 'SCORE_CHANGED') {
    return (
      <span className="muted">
        {detail.from} → <b>{detail.to}</b>{' '}
        ({detail.from_level} → {detail.to_level})
      </span>
    )
  }
  return (
    <span className="muted">
      {Object.entries(detail)
        .filter(([, v]) => v !== null && v !== '' && v !== false)
        .map(([k, v]) => `${k.replace(/_/g, ' ')}: ${v}`)
        .join(' · ')}
    </span>
  )
}

export default function Audit() {
  const [entries, setEntries] = useState([])
  const [summary, setSummary] = useState(null)
  const [action, setAction] = useState('')
  const [search, setSearch] = useState('')
  const [error, setError] = useState('')

  const load = useCallback(() => {
    const params = new URLSearchParams({ page_size: '200' })
    if (action) params.set('action', action)
    if (search.trim()) params.set('search', search.trim())
    apiGet(`/api/audit/?${params}`)
      .then((d) => { setEntries(d.results || d); setError('') })
      .catch((e) => setError(e.message))
    apiGet('/api/audit/summary/').then(setSummary).catch(() => setSummary(null))
  }, [action, search])
  useEffect(load, [load])

  if (error) return <div className="error">{error}</div>

  return (
    <div>
      <div className="card">
        <h3>Audit log</h3>
        <p className="muted">
          Who changed what, and when. Append-only — there is no way to edit or delete an
          entry, here or through the API. Records the decisions a school would be asked
          about later: a mark corrected, a learner removed from the register, a report
          approved, a promotion run, rights granted, a password reset.
        </p>
        <p style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <select value={action} onChange={(e) => setAction(e.target.value)}>
            <option value="">All actions{summary ? ` (${summary.total})` : ''}</option>
            {(summary?.actions || []).map((a) => (
              <option key={a.action} value={a.action}>
                {a.label} ({a.count})
              </option>
            ))}
          </select>
          <input
            placeholder="Search by name or who did it"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ padding: '0.4rem', minWidth: '18rem' }}
          />
        </p>
      </div>

      <div className="card">
        {entries.length === 0 ? (
          <p className="muted">Nothing recorded yet.</p>
        ) : (
          <table>
            <thead>
              <tr><th>When</th><th>Who</th><th>What</th><th>Which</th><th>Detail</th></tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.id}>
                  <td className="muted" style={{ whiteSpace: 'nowrap' }}>
                    {new Date(e.created_at).toLocaleString()}
                  </td>
                  <td>{e.actor_name || <span className="muted">system</span>}</td>
                  <td>
                    <span className={`badge ${SERIOUS.has(e.action) ? 'offline' : 'queued'}`}>
                      {e.action_label}
                    </span>
                  </td>
                  <td>{e.label}</td>
                  <td><Detail action={e.action} detail={e.detail} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
