import { useEffect, useState } from 'react'
import { apiGet, apiWrite } from './api.js'

/**
 * A slim bar across the top of the staff portals when the subscription is
 * running out or has run out. Amber counts down the last days; red marks
 * read-only and offers the leadership a one-tap "request extension" that pings
 * the operator. Renders nothing the rest of the time, so it is safe to drop in
 * at the top of any staff view. Never shown to parents — renewal is the
 * school's business, not a family's.
 */
export default function SubscriptionBanner() {
  const [s, setS] = useState(null)
  const [sent, setSent] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    apiGet('/api/my-school/standing/').then(setS).catch(() => setS(null))
  }, [])

  if (!s || !s.state) return null

  const soon =
    (s.state === 'ACTIVE' || s.state === 'TRIAL') &&
    s.days_left != null && s.days_left >= 0 && s.days_left <= 7
  const lapsed = s.state === 'READ_ONLY'
  const grace = s.state === 'GRACE'
  if (!soon && !lapsed && !grace) return null

  const tone = lapsed ? 'sub-banner-red' : grace ? 'sub-banner-red' : 'sub-banner-amber'

  async function request() {
    setBusy(true)
    const res = await apiWrite('/api/my-school/request-extension/', {})
    setBusy(false)
    if (res.ok) setSent(true)
  }

  return (
    <div className={`sub-banner ${tone}`}>
      <span>
        {soon && (
          <>Your ShuleNest subscription ends in <b>{s.days_left} day{s.days_left === 1 ? '' : 's'}</b>. Renew to avoid read-only mode.</>
        )}
        {grace && (
          <>Your subscription has lapsed — you're in a short grace period. Renew now to keep editing.</>
        )}
        {lapsed && (
          <><b>Read-only:</b> your subscription has lapsed. Your data is safe and visible, but nothing can be edited until you renew.</>
        )}
      </span>
      {s.can_request && (sent ? (
        <span className="sub-banner-ok">Request sent ✓</span>
      ) : (
        <button onClick={request} disabled={busy}>
          {busy ? 'Sending…' : 'Request extension'}
        </button>
      ))}
    </div>
  )
}
