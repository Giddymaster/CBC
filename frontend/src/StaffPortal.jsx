import { useCallback, useEffect, useState } from 'react'
import { apiGet, apiWrite } from './api.js'
import { gradeLabel } from './format.js'
import Admission from './Admission.jsx'
import Fees from './Fees.jsx'
import Messaging from './Messaging.jsx'
import MyTeam from './MyTeam.jsx'
import { ChangePasswordForm } from './Password.jsx'
import Security from './Security.jsx'
import { ActionCard, ActionGrid, BackBar, BottomNav, PortalHero } from './portalUi.jsx'

const STATUS_BADGE = {
  DRAFT: 'queued', SUBMITTED: 'queued', APPROVED: 'online', RETURNED: 'offline',
}
const STATUS_LABEL = {
  DRAFT: 'Draft', SUBMITTED: 'Awaiting approval',
  APPROVED: 'Approved', RETURNED: 'Returned for changes',
}

function ReportStatus({ status }) {
  return <span className={`badge ${STATUS_BADGE[status]}`}>{STATUS_LABEL[status]}</span>
}

// Circular photo, or the person's initials when they haven't set one.
export function Avatar({ person, size = 'md' }) {
  const cls = `avatar avatar-${size}`
  if (person?.photo) {
    return <img className={cls} src={person.photo} alt={person.name} />
  }
  return <span className={cls}>{person?.initials || '?'}</span>
}

function Field({ label, children }) {
  return (
    <div className="profile-field">
      <span className="profile-label">{label}</span>
      <span className="profile-value">{children ?? <span className="muted">—</span>}</span>
    </div>
  )
}

// "What I do and who I report to"
export function MyRolePanel({ data, onRefresh }) {
  const r = data.responsibilities
  const me = data.me
  const [uploading, setUploading] = useState(false)
  const nothing =
    r.class_teacher_of.length === 0 && r.lessons.length === 0 &&
    r.facilities.length === 0 && r.duties.length === 0

  async function uploadPhoto(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    const fd = new FormData()
    fd.append('photo', file)
    const token = localStorage.getItem('cbc-token')
    await fetch('/api/my-portal/photo/', {
      method: 'POST',
      headers: token ? { Authorization: `Token ${token}` } : {},
      body: fd,
    })
    setUploading(false)
    onRefresh?.()
  }

  return (
    <div>
      <div className="card profile-card">
        <div className="profile-head">
          <div className="profile-photo">
            <Avatar person={me} size="lg" />
            <label className="photo-upload">
              {uploading ? 'Uploading…' : me.photo ? 'Change photo' : 'Add photo'}
              <input type="file" accept="image/*" onChange={uploadPhoto} hidden />
            </label>
          </div>
          <div className="profile-headline">
            <h3>{me.name}</h3>
            <p className="profile-title">{me.title}</p>
            <p className="muted">
              {me.department} · {me.kind_label}
            </p>
          </div>
        </div>

        <div className="profile-grid">
          <Field label="Staff No">{me.staff_no || null}</Field>
          <Field label="Employment">{me.employment}</Field>
          <Field label="Phone">
            {me.phone ? <a href={`tel:${me.phone}`}>{me.phone}</a> : null}
          </Field>
          <Field label="Email">{me.email || null}</Field>
          <Field label="School">{me.school}</Field>
          <Field label="Username">{me.username}</Field>
        </div>

        <div className="profile-line">
          <div className="profile-line-block">
            <span className="profile-label">Supervisor</span>
            {data.supervisor ? (
              <div className="person-chip">
                <Avatar person={data.supervisor} size="sm" />
                <div>
                  <div><b>{data.supervisor.name}</b></div>
                  <div className="muted">
                    {data.supervisor.title}
                    {data.supervisor.phone && (
                      <> · <a href={`tel:${data.supervisor.phone}`}>{data.supervisor.phone}</a></>
                    )}
                  </div>
                </div>
              </div>
            ) : (
              <p className="muted">Not assigned — ask the admin to set one.</p>
            )}
          </div>

          {data.supervises.length > 0 && (
            <div className="profile-line-block">
              <span className="profile-label">Reports to me ({data.supervises.length})</span>
              <div className="person-row">
                {data.supervises.map((p) => (
                  <div className="person-chip" key={p.id}>
                    <Avatar person={p} size="sm" />
                    <div>
                      <div>{p.name}</div>
                      <div className="muted">{p.title}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {data.my_tasks?.length > 0 && (
        <div className="card">
          <h3>Work assigned to me ({data.my_tasks.filter((t) => t.status !== 'DONE').length} open)</h3>
          <table>
            <thead>
              <tr><th>Task</th><th>From</th><th>Due</th><th>Priority</th><th>Status</th></tr>
            </thead>
            <tbody>
              {data.my_tasks.map((t) => (
                <tr key={t.id}>
                  <td>{t.title}{t.description && <div className="muted">{t.description}</div>}</td>
                  <td className="muted">{t.assigned_by_name}</td>
                  <td className="muted">{t.due_date || '—'}</td>
                  <td>{t.priority === 'HIGH' ? <span className="badge offline">High</span> : 'Normal'}</td>
                  <td>
                    <select
                      value={t.status}
                      onChange={async (e) => {
                        await apiWrite(`/api/staff-tasks/${t.id}/`, { status: e.target.value }, { method: 'PATCH' })
                        onRefresh?.()
                      }}
                    >
                      <option value="OPEN">Open</option>
                      <option value="DOING">In progress</option>
                      <option value="DONE">Done</option>
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="card">
        <h3>My password</h3>
        <p className="muted">
          Change it whenever you like. Other devices will need to sign in again.
        </p>
        <ChangePasswordForm />
      </div>

      <Security />

      <div className="card">
        <h3>My responsibilities</h3>
        {nothing && <p className="muted">Nothing assigned yet.</p>}

        {r.class_teacher_of.length > 0 && (
          <p>
            <b>Class teacher of:</b>{' '}
            {r.class_teacher_of.map((c) => `${c.label} (${c.learners} learners)`).join(', ')}
          </p>
        )}

        {r.lessons.length > 0 && (
          <>
            <p><b>Lessons I teach</b></p>
            <table>
              <thead>
                <tr><th>Subject</th><th>Class</th><th>Lessons / week</th></tr>
              </thead>
              <tbody>
                {r.lessons.map((l, i) => (
                  <tr key={i}>
                    <td>{l.subject}</td>
                    <td>{gradeLabel(l.grade)}{l.stream}</td>
                    <td>{l.lessons_per_week}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}

        {r.facilities.length > 0 && (
          <>
            <p><b>Facilities I look after</b></p>
            <table>
              <thead>
                <tr><th>Facility</th><th>My position</th><th>Supplies</th><th>Needs attention</th></tr>
              </thead>
              <tbody>
                {r.facilities.map((f) => (
                  <tr key={f.id}>
                    <td>{f.facility}<div className="muted">{f.category}</div></td>
                    <td>{f.position}</td>
                    <td>{f.supplies_total}</td>
                    <td>
                      {f.supplies_depleted.length > 0 && (
                        <span className="badge offline">
                          Depleted: {f.supplies_depleted.join(', ')}
                        </span>
                      )}{' '}
                      {f.supplies_low.length > 0 && (
                        <span className="badge queued">Low: {f.supplies_low.join(', ')}</span>
                      )}
                      {f.supplies_depleted.length === 0 && f.supplies_low.length === 0 && (
                        <span className="badge online">All stocked</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}

        {r.duties.length > 0 && (
          <>
            <p><b>Other duties</b></p>
            {r.duties.map((d) => (
              <p key={d.id}>
                {d.title}
                {d.description && <span className="muted"> — {d.description}</span>}
              </p>
            ))}
          </>
        )}
      </div>
    </div>
  )
}

// Submitting reports up the line, and approving those that come down it.
export function ReportsPanel({ data, onRefresh }) {
  const [form, setForm] = useState({ title: '', period: '', body: '' })
  const [message, setMessage] = useState('')
  const [comments, setComments] = useState({})

  const setField = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  async function createAndSubmit(e, submit) {
    e.preventDefault()
    if (!form.title.trim()) {
      setMessage('Give the report a title.')
      return
    }
    const created = await apiWrite('/api/staff-reports/', form)
    if (!created.ok) {
      setMessage(`Failed: ${JSON.stringify(created.data)}`)
      return
    }
    if (submit) {
      const sent = await apiWrite(`/api/staff-reports/${created.data.id}/submit/`, {})
      setMessage(
        sent.ok
          ? `Sent to ${data.supervisor?.name || 'your supervisor'} for approval.`
          : sent.data?.detail || 'Saved, but could not submit.',
      )
    } else {
      setMessage('Saved as draft.')
    }
    setForm({ title: '', period: '', body: '' })
    onRefresh()
  }

  async function submitExisting(report) {
    const res = await apiWrite(`/api/staff-reports/${report.id}/submit/`, {})
    setMessage(res.ok ? 'Submitted for approval.' : res.data?.detail || 'Could not submit.')
    onRefresh()
  }

  async function review(report, decision) {
    const res = await apiWrite(`/api/staff-reports/${report.id}/review/`, {
      decision,
      comment: comments[report.id] || '',
    })
    setMessage(
      res.ok
        ? `Report ${decision === 'approve' ? 'approved' : 'returned'}.`
        : res.data?.detail || 'Could not review.',
    )
    onRefresh()
  }

  return (
    <div>
      {data.reports.to_review.length > 0 && (
        <div className="card">
          <h3>Awaiting my approval ({data.reports.to_review.length})</h3>
          {data.reports.to_review.map((r) => (
            <div key={r.id} style={{ borderBottom: '1px solid #e2e8f0', paddingBottom: '0.6rem', marginBottom: '0.6rem' }}>
              <p>
                <b>{r.title}</b> <span className="muted">
                  from {r.author_name}{r.period ? ` · ${r.period}` : ''}
                </span>
              </p>
              {r.body && <p>{r.body}</p>}
              {r.document && <p><a href={r.document} target="_blank" rel="noreferrer">Open attachment</a></p>}
              <p style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                <input
                  placeholder="Comment (optional for approval)"
                  style={{ flex: 1, minWidth: '14rem', padding: '0.4rem' }}
                  value={comments[r.id] || ''}
                  onChange={(e) => setComments({ ...comments, [r.id]: e.target.value })}
                />
                <button className="primary" onClick={() => review(r, 'approve')}>Approve</button>
                <button onClick={() => review(r, 'return')}>Return for changes</button>
              </p>
            </div>
          ))}
        </div>
      )}

      <div className="card">
        <h3>Write a report</h3>
        <p className="muted">
          Goes to {data.supervisor ? <b>{data.supervisor.name}</b> : 'your supervisor'} for approval.
        </p>
        <form style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'flex-start' }}>
          <input placeholder="Title e.g. Kitchen weekly report" value={form.title}
            onChange={setField('title')} style={{ padding: '0.4rem', minWidth: '16rem' }} />
          <input placeholder="Period e.g. Week 5, Term 2" value={form.period}
            onChange={setField('period')} style={{ padding: '0.4rem' }} />
          <textarea placeholder="What happened, what is needed…" value={form.body}
            onChange={setField('body')} rows={3}
            style={{ padding: '0.4rem', width: '100%', boxSizing: 'border-box' }} />
          <button className="primary" onClick={(e) => createAndSubmit(e, true)}>
            Submit for approval
          </button>
          <button onClick={(e) => createAndSubmit(e, false)}>Save as draft</button>
        </form>
        {message && <p className="muted">{message}</p>}
      </div>

      <div className="card">
        <h3>My reports</h3>
        {data.reports.mine.length === 0 && <p className="muted">No reports yet.</p>}
        {data.reports.mine.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>Title</th><th>Period</th><th>Status</th><th>Reviewed by</th>
                <th>Feedback</th><th></th>
              </tr>
            </thead>
            <tbody>
              {data.reports.mine.map((r) => (
                <tr key={r.id}>
                  <td>{r.title}</td>
                  <td className="muted">{r.period || '—'}</td>
                  <td><ReportStatus status={r.status} /></td>
                  <td className="muted">{r.reviewed_by_name || '—'}</td>
                  <td className="muted">{r.review_comment || '—'}</td>
                  <td>
                    {(r.status === 'DRAFT' || r.status === 'RETURNED') && (
                      <button onClick={() => submitExisting(r)}>Submit</button>
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

// Portal for non-teaching staff — cooks, drivers, matrons, bursar, security.
export default function SupportPortal() {
  const [data, setData] = useState(null)
  const [access, setAccess] = useState(null)
  const [error, setError] = useState('')
  const [tab, setTab] = useState('Dashboard')

  const load = useCallback(() => {
    apiGet('/api/my-portal/').then(setData).catch((e) => setError(e.message))
    apiGet('/api/admissions/access/').then(setAccess).catch(() => setAccess(null))
  }, [])
  useEffect(load, [load])

  if (error) return <div className="error">{error}</div>
  if (!data) return <p className="muted">Loading…</p>

  const pending = data.reports.to_review.length
  const teamSize = data.team?.size || 0
  const canAdmit = Boolean(access?.can_admit)
  const canViewFees = Boolean(data.fees?.can_view)
  const canHandleFees = Boolean(data.fees?.can_handle)

  const actions = [
    { tab: 'My Role', icon: 'user', tone: 'blue', title: 'My Role',
      desc: 'Your duties, tasks and messages from your supervisor.', cta: 'View role' },
    ...(teamSize ? [{ tab: 'My Team', icon: 'users', tone: 'teal', title: 'My Team',
      desc: 'The staff who report to you.', cta: 'Open team', badge: teamSize }] : []),
    { tab: 'Reports', icon: 'file', tone: 'orange', title: 'Reports',
      desc: 'Weekly staff reports — yours, and any waiting on you.',
      cta: 'Open reports', badge: pending },
    ...(canAdmit ? [{ tab: 'Admissions', icon: 'plus', tone: 'green', title: 'Admissions',
      desc: 'Admit a learner into the school.', cta: 'Admit a learner' }] : []),
    // The bursar's own desk: receipt fees, chase balances, print the register.
    ...(canViewFees ? [{ tab: 'Fees', icon: 'wallet', tone: 'orange', title: 'Fees',
      desc: canHandleFees
        ? 'Receipt payments, raise invoices and print the fee register.'
        : 'What each class owes and has paid.',
      cta: canHandleFees ? 'Open the fees desk' : 'Open the register' }] : []),
    // Fee reminders are the school's commonest notice, so the bursar composes
    // them from their own desk rather than queueing at the office.
    ...(canHandleFees ? [{ tab: 'Messages', icon: 'chat', tone: 'blue',
      title: 'Message Parents',
      desc: 'Send an SMS or WhatsApp notice — a class, or only those still owing.',
      cta: 'Compose a message' }] : []),
  ]
  const nav = [
    { key: 'Dashboard', label: 'Dashboard', icon: 'grid' },
    { key: 'My Role', label: 'My Role', icon: 'user' },
    { key: 'Reports', label: 'Reports', icon: 'file' },
    ...(teamSize ? [{ key: 'My Team', label: 'Team', icon: 'users' }] : []),
    ...(canAdmit ? [{ key: 'Admissions', label: 'Admit', icon: 'plus' }] : []),
    ...(canViewFees ? [{ key: 'Fees', label: 'Fees', icon: 'wallet' }] : []),
  ]
  const openTab = (name) => { setTab(name); window.scrollTo(0, 0) }

  return (
    <div className="portal-shell">
      {tab !== 'Dashboard' && (
        <BackBar
          title={actions.find((a) => a.tab === tab)?.title || tab}
          onBack={() => openTab('Dashboard')}
        />
      )}

      {tab === 'Dashboard' && (
        <>
          <PortalHero
            icon="user"
            title={data.me.name}
            subtitle={`${data.me.title} · ${data.me.school}`}
            chips={[
              ...(pending ? [`${pending} report${pending === 1 ? '' : 's'} to review`] : []),
              ...(teamSize ? [`Team of ${teamSize}`] : []),
            ]}
          />
          <ActionGrid>
            {actions.map((a) => (
              <ActionCard key={a.tab} icon={a.icon} tone={a.tone} title={a.title}
                desc={a.desc} cta={a.cta} badge={a.badge || 0}
                onOpen={() => openTab(a.tab)} />
            ))}
          </ActionGrid>
        </>
      )}

      {tab === 'My Role' && <MyRolePanel data={data} onRefresh={load} />}
      {tab === 'My Team' && <MyTeam />}
      {tab === 'Admissions' && <Admission onAdmitted={load} />}
      {tab === 'Fees' && <Fees grade={null} canHandle={canHandleFees} />}
      {tab === 'Messages' && <Messaging grade={null} />}
      {tab === 'Reports' && <ReportsPanel data={data} onRefresh={load} />}

      <BottomNav items={nav} active={tab} onSelect={openTab} />
    </div>
  )
}
