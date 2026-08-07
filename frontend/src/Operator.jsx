import { useCallback, useEffect, useState } from 'react'
import { apiGet, apiWrite, clearToken } from './api.js'

// The 47 counties, so county is picked from a fixed list rather than typed.
// Sub-county, ward and zone stay free text: a complete, accurate ward dataset
// (~1,450 of them) belongs in a vetted lookup, not hard-coded from memory.
const KE_COUNTIES = [
  'Mombasa', 'Kwale', 'Kilifi', 'Tana River', 'Lamu', 'Taita-Taveta', 'Garissa',
  'Wajir', 'Mandera', 'Marsabit', 'Isiolo', 'Meru', 'Tharaka-Nithi', 'Embu',
  'Kitui', 'Machakos', 'Makueni', 'Nyandarua', 'Nyeri', 'Kirinyaga', "Murang'a",
  'Kiambu', 'Turkana', 'West Pokot', 'Samburu', 'Trans Nzoia', 'Uasin Gishu',
  'Elgeyo-Marakwet', 'Nandi', 'Baringo', 'Laikipia', 'Nakuru', 'Narok', 'Kajiado',
  'Kericho', 'Bomet', 'Kakamega', 'Vihiga', 'Bungoma', 'Busia', 'Siaya', 'Kisumu',
  'Homa Bay', 'Migori', 'Kisii', 'Nyamira', 'Nairobi',
]

const LEVELS = [
  ['', '—'], ['PRIMARY', 'Primary'], ['JSS', 'Junior School'],
  ['SSS', 'Senior School'], ['COMPOSITE', 'Composite'],
]
// The MoE placement tier a school is gazetted as.
const CATEGORIES = [
  ['', '—'], ['NATIONAL', 'National'], ['EXTRA_COUNTY', 'Extra-County'],
  ['COUNTY', 'County'], ['SUB_COUNTY', 'Sub-County'],
]
const GENDERS = [['', '—'], ['MIXED', 'Mixed'], ['BOYS', 'Boys'], ['GIRLS', 'Girls']]
const ACCOMMODATION = [
  ['', '—'], ['DAY', 'Day'], ['BOARDING', 'Boarding'], ['DAY_BOARDING', 'Day & Boarding'],
]
const OWNERSHIP = [
  ['', '—'], ['PUBLIC', 'Public'], ['PRIVATE', 'Private'], ['FAITH', 'Faith-based / Sponsored'],
]

const STATE_BADGE = {
  TRIAL: 'queued', ACTIVE: 'online', GRACE: 'queued',
  READ_ONLY: 'offline', CANCELLED: 'offline',
}
const STATE_LABEL = {
  TRIAL: 'Trial', ACTIVE: 'Active', GRACE: 'In grace',
  READ_ONLY: 'Read-only (lapsed)', CANCELLED: 'Cancelled',
}

function money(n) {
  return `KES ${Number(n).toLocaleString()}`
}

function Overview() {
  const [data, setData] = useState(null)
  useEffect(() => { apiGet('/api/platform/overview/').then(setData).catch(() => {}) }, [])
  if (!data) return null
  return (
    <div className="op-stats">
      <div className="op-stat"><b>{data.schools}</b><span>schools</span></div>
      <div className="op-stat"><b>{data.learners_total ?? 0}</b><span>learners</span></div>
      <div className="op-stat">
        <b>{data.outstanding_invoices}</b><span>unpaid invoices</span>
      </div>
      <div className="op-stat">
        <b>{money(data.outstanding_amount)}</b><span>outstanding</span>
      </div>
      {Object.entries(data.by_state).map(([state, n]) => (
        <div className="op-stat" key={state}>
          <b>{n}</b><span>{STATE_LABEL[state] || state}</span>
        </div>
      ))}
    </div>
  )
}

const BLANK_SCHOOL = {
  name: '', code: '', kemis_code: '', level: '',
  county: '', subcounty: '', ward: '', zone: '',
  category: '', gender: '', accommodation: '', ownership: '',
  plan: '',
  admin_first_name: '', admin_last_name: '', admin_phone: '', admin_email: '',
}

function Selects({ label, value, onChange, options }) {
  return (
    <label className="adm-field"><span className="adm-label">{label}</span>
      <select value={value} onChange={onChange}>
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select></label>
  )
}

function Provision({ plans, onDone, onGoToPlans }) {
  const [form, setForm] = useState(BLANK_SCHOOL)
  const [result, setResult] = useState(null)
  const [message, setMessage] = useState('')
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  // Default the plan to the first available once plans have loaded.
  useEffect(() => {
    if (!form.plan && plans[0]) setForm((f) => ({ ...f, plan: plans[0].id }))
  }, [plans, form.plan])

  async function submit(e) {
    e.preventDefault()
    if (!form.plan) { setMessage('Choose a plan — create one on the Plans tab first.'); return }
    const res = await apiWrite('/api/platform/provision/', { ...form, plan: Number(form.plan) })
    if (res.ok) {
      setResult(res.data)
      setForm(BLANK_SCHOOL)
      onDone?.()
    } else {
      setMessage(res.data?.detail || JSON.stringify(res.data))
    }
  }

  if (plans.length === 0) {
    return (
      <div className="card">
        <h3>Register a school</h3>
        <p className="muted">
          You need a billing plan before you can register a school — it decides what
          they’re charged. Create one first.
        </p>
        <button className="primary" onClick={onGoToPlans}>Go to Plans</button>
      </div>
    )
  }

  if (result) {
    return (
      <div className="card">
        <h3>{result.school.name} is live</h3>
        <p>School code <b>{result.school.code}</b>. Hand these credentials to the school:</p>
        <p className="op-creds">
          Username <b>{result.admin.username}</b>
          {result.admin.generated_password && (
            <> · Password <b>{result.admin.generated_password}</b></>
          )}
        </p>
        <p className="muted">
          Shown once. They will be asked to set their own password on first sign-in.
          The school starts on a free trial.
        </p>
        <button className="primary" onClick={() => setResult(null)}>Register another</button>
      </div>
    )
  }

  return (
    <div className="card">
      <h3>Register a school</h3>
      <form onSubmit={submit} className="adm-grid">
        <label className="adm-field"><span className="adm-label">School name</span>
          <input value={form.name} onChange={set('name')} required /></label>
        <label className="adm-field"><span className="adm-label">MoE code</span>
          <input value={form.code} onChange={set('code')} required /></label>
        <label className="adm-field"><span className="adm-label">KEMIS / NEMIS code</span>
          <input value={form.kemis_code} onChange={set('kemis_code')} /></label>
        <Selects label="Level" value={form.level} onChange={set('level')} options={LEVELS} />

        <label className="adm-field"><span className="adm-label">County</span>
          <select value={form.county} onChange={set('county')} required>
            <option value="">Choose county…</option>
            {KE_COUNTIES.map((c) => <option key={c} value={c}>{c}</option>)}
          </select></label>
        <label className="adm-field"><span className="adm-label">Sub-county</span>
          <input value={form.subcounty} onChange={set('subcounty')} /></label>
        <label className="adm-field"><span className="adm-label">Ward</span>
          <input value={form.ward} onChange={set('ward')} /></label>
        <label className="adm-field"><span className="adm-label">Zone / location</span>
          <input value={form.zone} onChange={set('zone')} /></label>

        <Selects label="MoE category" value={form.category} onChange={set('category')} options={CATEGORIES} />
        <Selects label="Gender" value={form.gender} onChange={set('gender')} options={GENDERS} />
        <Selects label="Boarding" value={form.accommodation} onChange={set('accommodation')} options={ACCOMMODATION} />
        <Selects label="Ownership" value={form.ownership} onChange={set('ownership')} options={OWNERSHIP} />

        <label className="adm-field"><span className="adm-label">Plan</span>
          <select value={form.plan} onChange={set('plan')}>
            {plans.map((p) => (
              <option key={p.id} value={p.id}>{p.name} — {money(p.price_per_learner)}/learner</option>
            ))}
          </select></label>

        <label className="adm-field"><span className="adm-label">Admin first name</span>
          <input value={form.admin_first_name} onChange={set('admin_first_name')} required /></label>
        <label className="adm-field"><span className="adm-label">Admin last name</span>
          <input value={form.admin_last_name} onChange={set('admin_last_name')} required /></label>
        <label className="adm-field"><span className="adm-label">Admin phone</span>
          <input value={form.admin_phone} onChange={set('admin_phone')} /></label>
        <label className="adm-field"><span className="adm-label">Admin email</span>
          <input type="email" value={form.admin_email} onChange={set('admin_email')} /></label>
        <div className="adm-wide">
          <button className="primary" type="submit">Register &amp; start trial</button>
          {message && <span className="error"> {message}</span>}
        </div>
      </form>
    </div>
  )
}

function SchoolRow({ sub, onOpen }) {
  return (
    <tr>
      <td><b>{sub.school_name}</b><div className="muted">{sub.school_code}</div></td>
      <td>{sub.plan_name}</td>
      <td>{sub.learners}</td>
      <td><span className={`badge ${STATE_BADGE[sub.state]}`}>{STATE_LABEL[sub.state]}</span></td>
      <td>
        {sub.outstanding > 0
          ? <span className="badge offline">{sub.outstanding} unpaid</span>
          : <span className="muted">—</span>}
      </td>
      <td>{sub.days_left != null ? `${sub.days_left}d` : '—'}</td>
      <td><button onClick={() => onOpen(sub)}>Manage</button></td>
    </tr>
  )
}

function SchoolDetail({ sub, onBack, onChange }) {
  const [invoices, setInvoices] = useState([])
  const [message, setMessage] = useState('')
  const [form, setForm] = useState({ period_label: '', period_end: '', due_on: '' })

  const load = useCallback(() => {
    apiGet(`/api/platform/invoices/?subscription=${sub.id}`)
      .then((d) => setInvoices(d.results || d))
      .catch(() => setInvoices([]))
  }, [sub.id])
  useEffect(load, [load])

  async function raiseInvoice(e) {
    e.preventDefault()
    if (!form.period_label || !form.period_end) {
      setMessage('A period label and end date are needed.')
      return
    }
    const res = await apiWrite(`/api/platform/subscriptions/${sub.id}/invoice/`, form)
    setMessage(res.ok ? `Invoiced ${money(res.data.amount)} for ${res.data.learner_count} learners.` : 'Failed.')
    if (res.ok) { setForm({ period_label: '', period_end: '', due_on: '' }); load(); onChange?.() }
  }

  async function markPaid(inv) {
    const reference = window.prompt('Payment reference (M-Pesa code, bank ref)?') || ''
    const res = await apiWrite(`/api/platform/invoices/${inv.id}/mark-paid/`, { reference })
    setMessage(res.ok ? 'Marked paid. Access extended.' : 'Failed.')
    if (res.ok) { load(); onChange?.() }
  }

  async function cancel() {
    if (!window.confirm(`Cancel ${sub.school_name}? They keep read access.`)) return
    await apiWrite(`/api/platform/subscriptions/${sub.id}/cancel/`, {})
    onChange?.(); onBack()
  }

  return (
    <div>
      <p><button onClick={onBack}>← All schools</button></p>
      <div className="card">
        <h3>{sub.school_name} <span className={`badge ${STATE_BADGE[sub.state]}`}>{STATE_LABEL[sub.state]}</span></h3>
        <p className="muted">
          {sub.plan_name} · {sub.learners} active learners ·{' '}
          {sub.paid_through ? `paid through ${sub.paid_through}` : 'no term paid yet'}
          {sub.trial_ends_on && sub.state === 'TRIAL' && ` · trial ends ${sub.trial_ends_on}`}
        </p>
        {message && <p className="muted">{message}</p>}
        <form onSubmit={raiseInvoice} style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <input placeholder="Term 2 2026" value={form.period_label}
            onChange={(e) => setForm({ ...form, period_label: e.target.value })}
            style={{ padding: '0.4rem' }} />
          <label className="muted">Access through
            <input type="date" value={form.period_end}
              onChange={(e) => setForm({ ...form, period_end: e.target.value })} /></label>
          <label className="muted">Due
            <input type="date" value={form.due_on}
              onChange={(e) => setForm({ ...form, due_on: e.target.value })} /></label>
          <button className="primary" type="submit">Raise invoice</button>
          <button type="button" onClick={cancel}>Cancel school</button>
        </form>
      </div>

      <div className="card">
        <h3>Invoices</h3>
        {invoices.length === 0 ? <p className="muted">None yet.</p> : (
          <table>
            <thead><tr><th>Period</th><th>Learners</th><th>Amount</th><th>Status</th><th>Due</th><th></th></tr></thead>
            <tbody>
              {invoices.map((inv) => (
                <tr key={inv.id}>
                  <td>{inv.period_label}</td>
                  <td>{inv.learner_count}</td>
                  <td>{money(inv.amount)}</td>
                  <td>
                    <span className={`badge ${inv.status === 'PAID' ? 'online' : inv.overdue ? 'offline' : 'queued'}`}>
                      {inv.status === 'PAID' ? 'Paid' : inv.overdue ? 'Overdue' : inv.status}
                    </span>
                    {inv.payment_reference && <div className="muted">{inv.payment_reference}</div>}
                  </td>
                  <td className="muted">{inv.due_on || '—'}</td>
                  <td>
                    {inv.status === 'SENT' && (
                      <button onClick={() => markPaid(inv)}>Mark paid</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

function Announcements() {
  const [items, setItems] = useState([])
  const [form, setForm] = useState({ title: '', body: '', category: 'UPDATE' })
  const [message, setMessage] = useState('')

  const load = useCallback(() => {
    apiGet('/api/platform/announcements/?page_size=50')
      .then((d) => setItems(d.results || d)).catch(() => setItems([]))
  }, [])
  useEffect(load, [load])

  async function post(e) {
    e.preventDefault()
    if (!form.title.trim() || !form.body.trim()) { setMessage('Title and body needed.'); return }
    const res = await apiWrite('/api/platform/announcements/', form)
    setMessage(res.ok ? 'Posted to every school.' : 'Failed.')
    if (res.ok) { setForm({ title: '', body: '', category: 'UPDATE' }); load() }
  }

  return (
    <div className="card">
      <h3>Announce to schools</h3>
      <p className="muted">New features, updates, maintenance and billing notices — shown to every school admin.</p>
      <form onSubmit={post} style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', maxWidth: '40rem' }}>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <input placeholder="Title" value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            style={{ padding: '0.4rem', flex: 1 }} />
          <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
            <option value="FEATURE">New feature</option>
            <option value="UPDATE">Update</option>
            <option value="MAINTENANCE">Maintenance</option>
            <option value="BILLING">Billing</option>
            <option value="OTHER">Notice</option>
          </select>
        </div>
        <textarea rows="3" placeholder="Message" value={form.body}
          onChange={(e) => setForm({ ...form, body: e.target.value })} />
        <div><button className="primary" type="submit">Publish</button>
          {message && <span className="muted"> {message}</span>}</div>
      </form>
      {items.map((a) => (
        <p key={a.id}><b>{a.title}</b> <span className="muted">({a.category_label})</span><br />{a.body}</p>
      ))}
    </div>
  )
}

function Plans({ plans, onChange }) {
  const [form, setForm] = useState({
    name: '', price_per_learner: '', minimum_charge: '', trial_days: 30,
  })
  const [message, setMessage] = useState('')

  async function create(e) {
    e.preventDefault()
    if (!form.name.trim() || form.price_per_learner === '') {
      setMessage('A name and a price per learner are needed.')
      return
    }
    const res = await apiWrite('/api/platform/plans/', {
      name: form.name.trim(),
      price_per_learner: form.price_per_learner,
      minimum_charge: form.minimum_charge || 0,
      trial_days: Number(form.trial_days) || 30,
    })
    setMessage(res.ok ? 'Plan created.' : res.data ? JSON.stringify(res.data) : 'Failed.')
    if (res.ok) {
      setForm({ name: '', price_per_learner: '', minimum_charge: '', trial_days: 30 })
      onChange?.()
    }
  }

  return (
    <div className="card">
      <h3>Plans</h3>
      <p className="muted">
        What a school is billed — per active learner, each term — with a floor so a very
        small school still covers its cost. Create at least one before registering a school.
      </p>
      <form onSubmit={create} className="adm-grid" style={{ maxWidth: '44rem' }}>
        <label className="adm-field"><span className="adm-label">Plan name</span>
          <input value={form.name} placeholder="e.g. Standard"
            onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
        <label className="adm-field"><span className="adm-label">Price per learner / term (KES)</span>
          <input type="number" min="0" step="1" value={form.price_per_learner}
            onChange={(e) => setForm({ ...form, price_per_learner: e.target.value })} /></label>
        <label className="adm-field"><span className="adm-label">Minimum per term (KES)</span>
          <input type="number" min="0" step="1" value={form.minimum_charge}
            onChange={(e) => setForm({ ...form, minimum_charge: e.target.value })} /></label>
        <label className="adm-field"><span className="adm-label">Free-trial days</span>
          <input type="number" min="0" value={form.trial_days}
            onChange={(e) => setForm({ ...form, trial_days: e.target.value })} /></label>
        <div className="adm-wide">
          <button className="primary" type="submit">Create plan</button>
          {message && <span className="muted"> {message}</span>}
        </div>
      </form>

      {plans.length > 0 && (
        <table>
          <thead><tr><th>Plan</th><th>Per learner</th><th>Minimum</th><th>Trial</th></tr></thead>
          <tbody>
            {plans.map((p) => (
              <tr key={p.id}>
                <td><b>{p.name}</b></td>
                <td>{money(p.price_per_learner)}</td>
                <td>{money(p.minimum_charge)}</td>
                <td>{p.trial_days} days</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

export default function Operator({ me }) {
  const [tab, setTab] = useState('Schools')
  const [subs, setSubs] = useState([])
  const [plans, setPlans] = useState([])
  const [open, setOpen] = useState(null)

  const load = useCallback(() => {
    apiGet('/api/platform/subscriptions/?page_size=200')
      .then((d) => setSubs(d.results || d)).catch(() => setSubs([]))
    apiGet('/api/platform/plans/?page_size=50')
      .then((d) => setPlans(d.results || d)).catch(() => setPlans([]))
  }, [])
  useEffect(load, [load])

  return (
    <div className="admin-shell">
      <header className="topbar">
        <h1>CBC — Operator Console</h1>
        <div className="userlinks">
          <span>Signed in as <b>{(me.full_name || me.username).toUpperCase()}</b></span>
          <button onClick={() => { clearToken(); window.location.reload() }}>Log out</button>
        </div>
      </header>

      <div className="op-body">
        <Overview />
        <nav className="tabs">
          {['Schools', 'Register', 'Plans', 'Announcements'].map((t) => (
            <button key={t} className={tab === t ? 'active' : ''} onClick={() => { setTab(t); setOpen(null) }}>{t}</button>
          ))}
        </nav>

        {tab === 'Schools' && (
          open
            ? <SchoolDetail sub={open} onBack={() => setOpen(null)} onChange={load} />
            : (
              <div className="card">
                <h3>Schools ({subs.length})</h3>
                {subs.length === 0 ? <p className="muted">No schools yet — register one.</p> : (
                  <table>
                    <thead><tr>
                      <th>School</th><th>Plan</th><th>Learners</th><th>Status</th>
                      <th>Billing</th><th>Days left</th><th></th>
                    </tr></thead>
                    <tbody>
                      {subs.map((s) => <SchoolRow key={s.id} sub={s} onOpen={setOpen} />)}
                    </tbody>
                  </table>
                )}
              </div>
            )
        )}
        {tab === 'Register' && (
          <Provision plans={plans} onDone={load} onGoToPlans={() => setTab('Plans')} />
        )}
        {tab === 'Plans' && <Plans plans={plans} onChange={load} />}
        {tab === 'Announcements' && <Announcements />}
      </div>
    </div>
  )
}
