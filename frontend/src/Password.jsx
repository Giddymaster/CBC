import { useState } from 'react'
import { apiWrite, setToken } from './api.js'

function problems(data) {
  if (!data) return 'Could not change the password.'
  return Object.values(data)
    .flat()
    .filter((v) => typeof v === 'string')
    .join(' ')
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
        <input type="password" value={form.current} onChange={set('current')}
          autoComplete="current-password" />
      </label>
      <label className="adm-field">
        <span className="adm-label">New password</span>
        <input type="password" value={form.next} onChange={set('next')}
          autoComplete="new-password" />
        <span className="adm-hint">At least 8 characters, and not a common one.</span>
      </label>
      <label className="adm-field">
        <span className="adm-label">New password again</span>
        <input type="password" value={form.confirm} onChange={set('confirm')}
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

/** Shown instead of the app until an admin-issued password is replaced. */
export function ForcedPasswordChange({ name, onDone }) {
  return (
    <div className="forced-gate">
      <div className="card" style={{ maxWidth: '40rem', margin: '3rem auto' }}>
        <h3>Choose your own password</h3>
        <p className="muted">
          {name ? `${name}, the ` : 'The '}password you are signed in with was issued by
          the school admin, so somebody else knows it. Replace it before going on —
          nobody else will be able to sign in as you afterwards.
        </p>
        <ChangePasswordForm forced onDone={onDone} />
      </div>
    </div>
  )
}

export default ChangePasswordForm
