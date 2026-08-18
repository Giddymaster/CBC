import { useEffect, useState } from 'react'
import { PasswordInput } from './Password.jsx'

/**
 * Forgot-password, both halves.
 *
 * <ForgotPassword> is the "I can't sign in" flow reached from the login page:
 * type your email or phone, then — if you gave a phone — enter the texted code
 * and a new password. If you gave an email, we tell you to open the link.
 *
 * <ResetByLink> is the page that email link opens (/verify/<token>): it confirms
 * what the link is for, then takes a new password against the token.
 *
 * The API never says whether an account exists, so neither does this screen.
 */

async function post(path, body) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return { ok: res.ok, data: await res.json().catch(() => ({})) }
}

export function ForgotPassword({ onBack }) {
  const [identifier, setIdentifier] = useState('')
  const [stage, setStage] = useState('ask') // ask | choose | code | none | done
  const [options, setOptions] = useState([])
  const [picked, setPicked] = useState('')
  const [sentTo, setSentTo] = useState(null) // {channel, target}
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function sendVia(channel, target) {
    setBusy(true)
    const res = await post('/api/password-reset/request/', { identifier, channel })
    setBusy(false)
    if (!res.ok) { setError('Something went wrong. Try again.'); return }
    setSentTo({ channel, target })
    setCode('')
    setStage('code')
  }

  // Step 1: look up where a reset can go. One contact → send straight there.
  // Two → offer the choice. None → the neutral "if that account exists" page.
  async function lookup(e) {
    e.preventDefault()
    setError('')
    setBusy(true)
    const res = await post('/api/password-reset/options/', { identifier })
    setBusy(false)
    if (!res.ok) { setError('Something went wrong. Try again.'); return }
    const found = res.data.options || []
    if (found.length === 0) { setStage('none'); return }
    if (found.length === 1) {
      await sendVia(found[0].channel, found[0].target)
      return
    }
    setOptions(found)
    setPicked(found[0].channel)
    setStage('choose')
  }

  async function confirm(e) {
    e.preventDefault()
    setError('')
    setBusy(true)
    const res = await post('/api/password-reset/confirm/', {
      identifier, code, new_password: password,
    })
    setBusy(false)
    if (res.ok) setStage('done')
    else setError(res.data.detail || Object.values(res.data).flat().join(' '))
  }

  if (stage === 'done') {
    return (
      <div className="login">
        <img src="/logo.svg" alt="ShuleNest" className="login-logo" />
        <h2>Password set</h2>
        <p className="muted">You can now sign in with your new password.</p>
        <button className="primary" onClick={onBack}>Back to sign in</button>
      </div>
    )
  }

  if (stage === 'none') {
    return (
      <div className="login">
        <img src="/logo.svg" alt="ShuleNest" className="login-logo" />
        <h2>Check with your school</h2>
        <p className="muted">
          If that account exists, it has no phone or email on file to send a
          reset to. Ask the school office to reset your password, then add a
          phone or email under Security so next time you can do it yourself.
        </p>
        <button onClick={onBack}>Back to sign in</button>
      </div>
    )
  }

  if (stage === 'choose') {
    return (
      <form className="login" onSubmit={(e) => { e.preventDefault(); const opt = options.find((o) => o.channel === picked); sendVia(opt.channel, opt.target) }}>
        <img src="/logo.svg" alt="ShuleNest" className="login-logo" />
        <h2>Where should the code go?</h2>
        {options.map((opt) => (
          <label key={opt.channel} className="fp-option">
            <input type="radio" name="fp-channel" value={opt.channel}
              checked={picked === opt.channel}
              onChange={() => setPicked(opt.channel)} />
            <span>
              {opt.channel === 'SMS' ? 'Text message to ' : 'Email to '}
              <b>{opt.target}</b>
            </span>
          </label>
        ))}
        <button className="primary" type="submit" disabled={busy}>
          {busy ? 'Sending…' : 'Send code'}
        </button>
        <button type="button" onClick={onBack}>Back to sign in</button>
        {error && <div className="error">{error}</div>}
      </form>
    )
  }

  if (stage === 'code') {
    return (
      <form className="login" onSubmit={confirm}>
        <img src="/logo.svg" alt="ShuleNest" className="login-logo" />
        <h2>Enter the code</h2>
        <p className="muted">
          {sentTo?.channel === 'SMS'
            ? `We texted a 6-digit code to ${sentTo.target}.`
            : `We emailed ${sentTo?.target} — enter the code from the email, or just tap its link.`}
        </p>
        <input placeholder="6-digit code" value={code} inputMode="numeric"
          maxLength={6} autoFocus
          onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} />
        <PasswordInput placeholder="New password" value={password}
          autoComplete="new-password"
          onChange={(e) => setPassword(e.target.value)} />
        <button className="primary" type="submit" disabled={busy || code.length !== 6 || !password}>
          {busy ? 'Setting…' : 'Set new password'}
        </button>
        <button type="button" onClick={onBack}>Back to sign in</button>
        {error && <div className="error">{error}</div>}
      </form>
    )
  }

  return (
    <form className="login" onSubmit={lookup}>
      <img src="/logo.svg" alt="ShuleNest" className="login-logo" />
      <h2>Reset your password</h2>
      <p className="muted">
        Enter your username, or your child's admission number.
      </p>
      <input placeholder="Username or admission number" value={identifier}
        autoComplete="username"
        onChange={(e) => setIdentifier(e.target.value)} />
      <button className="primary" type="submit" disabled={busy || !identifier.trim()}>
        {busy ? 'Checking…' : 'Continue'}
      </button>
      <button type="button" onClick={onBack}>Back to sign in</button>
      {error && <div className="error">{error}</div>}
    </form>
  )
}

export function ResetByLink({ token, onDone }) {
  const [info, setInfo] = useState(null)   // null=loading, {valid}
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)
  const [contactDone, setContactDone] = useState(false)

  useEffect(() => {
    fetch(`/api/verify/${token}/`)
      .then((r) => r.json())
      .then(async (data) => {
        // A contact-verification link needs no form — tapping it IS the proof,
        // so confirm it immediately and just show the outcome.
        if (data.valid && (data.purpose === 'EMAIL_VERIFY' || data.purpose === 'PHONE_VERIFY')) {
          const res = await post('/api/verify/confirm-link/', { token })
          setContactDone(res.ok)
          setInfo(res.ok ? data : { valid: false })
          return
        }
        setInfo(data)
      })
      .catch(() => setInfo({ valid: false }))
  }, [token])

  async function submit(e) {
    e.preventDefault()
    setError('')
    setBusy(true)
    const res = await post('/api/password-reset/confirm/', { token, new_password: password })
    setBusy(false)
    if (res.ok) setDone(true)
    else setError(res.data.detail || Object.values(res.data).flat().join(' '))
  }

  if (info === null) return <div className="login"><p className="muted">Checking your link…</p></div>

  if (contactDone) {
    return (
      <div className="login">
        <img src="/logo.svg" alt="ShuleNest" className="login-logo" />
        <h2>{info.purpose === 'EMAIL_VERIFY' ? 'Email verified' : 'Phone verified'} ✓</h2>
        <p className="muted">
          {info.target} is confirmed for your account. You can close this page
          or go to sign in.
        </p>
        <button className="primary" onClick={onDone}>Go to sign in</button>
      </div>
    )
  }

  if (!info.valid) {
    return (
      <div className="login">
        <img src="/logo.svg" alt="ShuleNest" className="login-logo" />
        <h2>Link expired</h2>
        <p className="muted">This reset link is no longer valid. Start again from sign-in.</p>
        <button className="primary" onClick={onDone}>Back to sign in</button>
      </div>
    )
  }

  if (done) {
    return (
      <div className="login">
        <img src="/logo.svg" alt="ShuleNest" className="login-logo" />
        <h2>Password set</h2>
        <p className="muted">Sign in with your new password.</p>
        <button className="primary" onClick={onDone}>Go to sign in</button>
      </div>
    )
  }

  return (
    <form className="login" onSubmit={submit}>
      <img src="/logo.svg" alt="ShuleNest" className="login-logo" />
      <h2>Choose a new password</h2>
      <p className="muted">
        {info.name ? `${info.name}, ` : ''}for the account {info.target}.
      </p>
      <PasswordInput placeholder="New password" value={password}
        autoComplete="new-password"
        onChange={(e) => setPassword(e.target.value)} />
      <button className="primary" type="submit" disabled={busy || !password}>
        {busy ? 'Setting…' : 'Set password'}
      </button>
      {error && <div className="error">{error}</div>}
    </form>
  )
}
