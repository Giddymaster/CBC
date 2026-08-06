import { useCallback, useEffect, useState } from 'react'
import { apiGet, apiWrite } from './api.js'

const STATE_BADGE = {
  TRIAL: 'queued', ACTIVE: 'online', GRACE: 'queued',
  READ_ONLY: 'offline', CANCELLED: 'offline',
}
const STATE_LABEL = {
  TRIAL: 'Free trial', ACTIVE: 'Active', GRACE: 'Payment due',
  READ_ONLY: 'Lapsed — read-only', CANCELLED: 'Cancelled',
}

function money(n) {
  return `KES ${Number(n).toLocaleString()}`
}

/** A school admin's own subscription standing and invoices. */
export default function Subscription() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    apiGet('/api/my-school/subscription/')
      .then(setData)
      .catch((e) => setError(e.message))
  }, [])

  if (error) return <div className="error">{error}</div>
  if (!data) return <p className="muted">Loading…</p>
  if (!data.subscription) {
    return (
      <div className="card">
        <h3>Subscription</h3>
        <p className="muted">
          No subscription is on file for this school. Contact the platform operator.
        </p>
      </div>
    )
  }

  const s = data.subscription
  const outstanding = data.invoices.filter((i) => i.status === 'SENT')

  return (
    <div>
      <div className="card">
        <h3>
          Subscription{' '}
          <span className={`badge ${STATE_BADGE[s.state]}`}>{STATE_LABEL[s.state]}</span>
        </h3>
        <div className="profile-grid">
          <div className="profile-field">
            <span className="profile-label">Plan</span>
            <span className="profile-value">{s.plan_name}</span>
          </div>
          <div className="profile-field">
            <span className="profile-label">Active learners</span>
            <span className="profile-value">{s.learners}</span>
          </div>
          <div className="profile-field">
            <span className="profile-label">
              {s.state === 'TRIAL' ? 'Trial ends' : 'Paid through'}
            </span>
            <span className="profile-value">
              {s.state === 'TRIAL' ? (s.trial_ends_on || '—') : (s.paid_through || '—')}
            </span>
          </div>
          {s.days_left != null && (
            <div className="profile-field">
              <span className="profile-label">Days remaining</span>
              <span className="profile-value">{s.days_left}</span>
            </div>
          )}
        </div>

        {!s.can_write && (
          <p className="sync-note">
            Your subscription has lapsed, so the system is in <b>read-only</b> mode. All your
            data is safe and fully visible. Settle the invoice below to resume editing.
          </p>
        )}
      </div>

      <div className="card">
        <h3>Invoices</h3>
        {data.invoices.length === 0 ? (
          <p className="muted">No invoices yet.</p>
        ) : (
          <table>
            <thead>
              <tr><th>Period</th><th>Learners</th><th>Amount</th><th>Status</th><th>Due</th><th>Reference</th></tr>
            </thead>
            <tbody>
              {data.invoices.map((inv) => (
                <tr key={inv.id}>
                  <td>{inv.period_label}</td>
                  <td>{inv.learner_count}</td>
                  <td>{money(inv.amount)}</td>
                  <td>
                    <span className={`badge ${inv.status === 'PAID' ? 'online' : inv.overdue ? 'offline' : 'queued'}`}>
                      {inv.status === 'PAID' ? 'Paid' : inv.overdue ? 'Overdue' : 'Awaiting payment'}
                    </span>
                  </td>
                  <td className="muted">{inv.due_on || '—'}</td>
                  <td className="muted">{inv.payment_reference || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {outstanding.length > 0 && (
          <p className="muted">
            Pay the operator and they will mark the invoice settled — your access extends
            as soon as they do.
          </p>
        )}
      </div>
    </div>
  )
}

/** Banner of unread operator announcements, dismissible. Shown atop the admin shell. */
export function PlatformAnnouncements() {
  const [items, setItems] = useState([])

  const load = useCallback(() => {
    apiGet('/api/platform-announcements/')
      .then((d) => setItems((d.items || []).filter((i) => !i.seen)))
      .catch(() => setItems([]))
  }, [])
  useEffect(load, [load])

  async function dismiss() {
    await apiWrite('/api/platform-announcements/', {})
    setItems([])
  }

  if (items.length === 0) return null

  return (
    <div className="platform-banner">
      <div>
        {items.map((a) => (
          <div key={a.id} className="platform-item">
            <span className="badge queued">{a.category_label}</span>{' '}
            <b>{a.title}</b> — {a.body}
            {a.link && <> <a href={a.link} target="_blank" rel="noreferrer">Read more</a></>}
          </div>
        ))}
      </div>
      <button onClick={dismiss}>Dismiss</button>
    </div>
  )
}
