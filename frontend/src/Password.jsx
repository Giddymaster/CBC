import { useEffect, useState } from 'react'
import { apiGet, apiWrite, setToken } from './api.js'

function problems(data) {
  if (!data) return 'Could not change the password.'
  return Object.values(data)
    .flat()
    .filter((v) => typeof v === 'string')
    .join(' ')
}

function EyeIcon({ off }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
      aria-hidden="true">
      <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z" />
      <circle cx="12" cy="12" r="3" />
      {off && <line x1="3" y1="3" x2="21" y2="21" />}
    </svg>
  )
}

/** A password box with an eye to peek at what you are typing — phone keyboards
 * make blind typing error-prone. Visibility resets on every mount. */
export function PasswordInput({ value, onChange, placeholder, autoComplete }) {
  const [show, setShow] = useState(false)
  return (
    <span className="pw-wrap">
      <input
        type={show ? 'text' : 'password'}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        autoComplete={autoComplete}
      />
      <button
        type="button"
        className="pw-eye"
        aria-label={show ? 'Hide password' : 'Show password'}
        title={show ? 'Hide password' : 'Show password'}
        onClick={() => setShow((s) => !s)}
      >
        <EyeIcon off={show} />
      </button>
    </span>
  )
}

/** The form itself — reused by the settings panel and the forced-change gate. */
export function ChangePasswordForm({ onDone, forced }) {
  const [form, setForm] = useState({ current: '', next: '', confirm: '' })
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))

  async function submit(e) {
    e.preventDefault()
    if (form.next !== form.confirm) {
      setMessage('The two new passwords do not match.')
      return
    }
    setBusy(true)
    const res = await apiWrite('/api/me/password/', {
      current_password: form.current,
      new_password: form.next,
    })
    setBusy(false)
    if (!res.ok) {
      setMessage(problems(res.data))
      return
    }
    // The server rotated the token; keep this session signed in with the new one.
    if (res.data?.token) setToken(res.data.token)
    setForm({ current: '', next: '', confirm: '' })
    setMessage('Password changed. Any other device will need to sign in again.')
    onDone?.()
  }

  return (
    <form onSubmit={submit} className="adm-grid" style={{ maxWidth: '34rem' }}>
      <label className="adm-field">
        <span className="adm-label">
          {forced ? 'The password you were given' : 'Current password'}
        </span>
        <PasswordInput value={form.current} onChange={set('current')}
          autoComplete="current-password" />
      </label>
      <label className="adm-field">
        <span className="adm-label">New password</span>
        <PasswordInput value={form.next} onChange={set('next')}
          autoComplete="new-password" />
        <span className="adm-hint">At least 8 characters, and not a common one.</span>
      </label>
      <label className="adm-field">
        <span className="adm-label">New password again</span>
        <PasswordInput value={form.confirm} onChange={set('confirm')}
          autoComplete="new-password" />
      </label>
      <div className="adm-wide">
        <button className="primary" type="submit" disabled={busy}>
          {busy ? 'Saving…' : 'Change password'}
        </button>
        {message && <span className="muted"> {message}</span>}
      </div>
    </form>
  )
}

/** After the password is set: capture where a reset or sign-in code can reach
 * this person. Optional, but this is the one moment every account passes
 * through — a parent who skips it has no email on file when they later tap
 * "Forgot password". Changing a contact clears its verified flag server-side
 * and sends a verification straight away. */
function ContactCapture({ onDone }) {
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [initialPhone, setInitialPhone] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    apiGet('/api/me/')
      .then((me) => { setPhone(me.phone || ''); setInitialPhone(me.phone || ''); setEmail(me.email || '') })
      .catch(() => {})
  }, [])

  async function save() {
    setBusy(true)
    setMessage('')
    let failed = ''
    if (email.trim()) {
      const res = await apiWrite('/api/me/contact/', { email: email.trim() })
      if (!res.ok) failed = Object.values(res.data || {}).flat().join(' ')
    }
    if (!failed && phone.trim() && phone.trim() !== initialPhone) {
      const res = await apiWrite('/api/me/contact/', { phone: phone.trim() })
      if (!res.ok) failed = Object.values(res.data || {}).flat().join(' ')
    }
    setBusy(false)
    if (failed) { setMessage(failed); return }
    onDone()
  }

  return (
    <div className="forced-gate">
      <div className="card" style={{ maxWidth: '40rem', margin: '3rem auto' }}>
        <h3>How can we reach you?</h3>
        <p className="muted">
          If you ever forget your password, the reset code goes to these. Add an
          email (optional) and check your phone number is right — we'll send a
          quick verification to anything new.
        </p>
        <div className="adm-grid" style={{ maxWidth: '34rem' }}>
          <label className="adm-field">
            <span className="adm-label">Email (optional)</span>
            <input type="email" placeholder="name@example.com" value={email}
              autoComplete="email"
              onChange={(e) => setEmail(e.target.value)} />
          </label>
          <label className="adm-field">
            <span className="adm-label">Phone number</span>
            <input inputMode="tel" placeholder="07XX XXX XXX" value={phone}
              autoComplete="tel"
              onChange={(e) => setPhone(e.target.value)} />
          </label>
          <div className="adm-wide">
            <button className="primary" onClick={save} disabled={busy}>
              {busy ? 'Saving…' : 'Save and continue'}
            </button>
            <button onClick={onDone} disabled={busy} style={{ marginLeft: '0.5rem' }}>
              Skip for now
            </button>
            {message && <span className="muted"> {message}</span>}
          </div>
        </div>
      </div>
    </div>
  )
}

/** Shown instead of the app until an admin-issued password is replaced. */
export function ForcedPasswordChange({ name, onDone }) {
  const [passwordDone, setPasswordDone] = useState(false)

  if (passwordDone) return <ContactCapture onDone={onDone} />

  return (
    <div className="forced-gate">
      <div className="card" style={{ maxWidth: '40rem', margin: '3rem auto' }}>
        <h3>Choose your own password</h3>
        <p className="muted">
          {name ? `${name}, the ` : 'The '}password you are signed in with was issued by
          the school admin, so somebody else knows it. Replace it before going on —
          nobody else will be able to sign in as you afterwards.
        </p>
        <ChangePasswordForm forced onDone={() => setPasswordDone(true)} />
      </div>
    </div>
  )
}

export default ChangePasswordForm
