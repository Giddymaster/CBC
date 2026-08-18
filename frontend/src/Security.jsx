import { useCallback, useEffect, useState } from 'react'
import { apiGet, apiWrite } from './api.js'

/**
 * The account's security card: verify your phone and email, then switch on
 * two-step sign-in.
 *
 * Verification is the ordinary loop — "Send code", type it back (the email one
 * can also be tapped as a link). The 2FA toggle only unlocks once a contact is
 * verified, and the server enforces the same rule: a sign-in code sent to an
 * unreachable channel would be a lockout, not a protection.
 */
export default function Security() {
  const [me, setMe] = useState(null)
  const [pending, setPending] = useState(null) // 'SMS' | 'EMAIL' while a code is out
  const [code, setCode] = useState('')
  const [message, setMessage] = useState('')

  const load = useCallback(() => {
    apiGet('/api/me/').then(setMe).catch(() => setMe(null))
  }, [])
  useEffect(load, [load])

  if (!me) return null
  const anyVerified = me.phone_verified || me.email_verified

  async function sendCode(channel) {
    setMessage('')
    const res = await apiWrite('/api/me/verify/request/', { channel })
    if (res.ok) {
      setPending(channel)
      setCode('')
      setMessage(
        channel === 'SMS'
          ? `Code sent to ${res.data.target}.`
          : `Sent to ${res.data.target} — tap the link in the email, or enter the code here.`,
      )
    } else {
      setMessage(res.data?.detail || 'Could not send the code.')
    }
  }

  async function confirm() {
    const res = await apiWrite('/api/me/verify/confirm/', { code })
    if (res.ok) {
      setPending(null)
      setCode('')
      setMessage('Verified ✓')
      load()
    } else {
      setMessage(res.data?.detail || 'That code is wrong or has expired.')
    }
  }

  async function toggle2fa() {
    setMessage('')
    const res = await apiWrite('/api/me/2fa/', { enabled: !me.two_factor_enabled })
    if (res.ok) load()
    else setMessage(res.data?.detail || 'Could not change the setting.')
  }

  const row = (label, value, verified, channel) => (
    <div className="sec-row">
      <div className="sec-contact">
        <small>{label}</small>
        <b>{value || <span className="muted">none on file</span>}</b>
      </div>
      {value && (verified ? (
        <span className="sec-ok">Verified ✓</span>
      ) : (
        <button onClick={() => sendCode(channel)}>Send code</button>
      ))}
    </div>
  )

  return (
    <div className="card">
      <h3>Security</h3>
      {row('Phone', me.phone, me.phone_verified, 'SMS')}
      {row('Email', me.email, me.email_verified, 'EMAIL')}

      {pending && (
        <div className="sec-row">
          <input placeholder="6-digit code" value={code} inputMode="numeric"
            maxLength={6}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
            style={{ padding: '0.45rem', width: '9rem' }} />
          <button className="primary" onClick={confirm} disabled={code.length !== 6}>
            Confirm
          </button>
        </div>
      )}

      <div className="sec-row sec-2fa">
        <div className="sec-contact">
          <small>Two-step sign-in</small>
          <b>{me.two_factor_enabled ? 'On — a code is asked at every sign-in' : 'Off'}</b>
        </div>
        <button className={me.two_factor_enabled ? '' : 'primary'}
          onClick={toggle2fa}
          disabled={!me.two_factor_enabled && !anyVerified}
          title={!anyVerified ? 'Verify your phone or email first' : ''}>
          {me.two_factor_enabled ? 'Turn off' : 'Turn on'}
        </button>
      </div>
      {!anyVerified && (
        <p className="muted" style={{ fontSize: '0.82rem' }}>
          Verify your phone or email first — sign-in codes need somewhere to go.
        </p>
      )}
      {message && <p className="muted">{message}</p>}
    </div>
  )
}
