import { useCallback, useEffect, useState } from 'react'
import { apiGet, apiWrite } from './api.js'
import { AddColumnHeader, ColumnHeader, columnApi } from './columns.jsx'

const PRESENT_LABEL = { P: 'Present', A: 'Absent', L: 'On leave' }
const PRESENT_BADGE = { P: 'online', A: 'offline', L: 'queued' }

const EMPTY_SUPPORT = {
  full_name: '', category: 'KITCHEN', title: '', phone: '', employment_type: 'BOM',
  supervisor: '', extra: {},
}
const EMPTY_TEACHER = {
  first_name: '', last_name: '', tsc_number: '', employment_type: 'TSC',
  rank: 'TEACHER', phone: '', username: '', password: '', supervisor: '', extra: {},
}

function PresenceBadge({ status }) {
  if (!status) return <span className="muted">Not marked</span>
  return <span className={`badge ${PRESENT_BADGE[status]}`}>{PRESENT_LABEL[status]}</span>
}

// Who this person reports to. Rank alone decides how *wide* a view is; this
// decides whose reports land on whose desk, so it belongs on the staff record.
function SupervisorSelect({ value, onChange, choices, excludeUserId }) {
  const options = (choices || []).filter((c) => c.id !== excludeUserId)
  return (
    <label className="muted" style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
      Supervisor
      <select value={value ?? ''} onChange={onChange}>
        <option value="">— none —</option>
        {options.map((c) => (
          <option key={c.id} value={c.id}>{c.name} ({c.kind})</option>
        ))}
      </select>
    </label>
  )
}

// Admitting a learner creates a permanent record with medical and next-of-kin
// detail, so it stays with the admin unless deliberately handed out.
function AdmissionRights({ supervisorChoices, onMessage }) {
  const [rights, setRights] = useState([])
  const [form, setForm] = useState({ user: '', note: '', expires_on: '' })
  const [open, setOpen] = useState(false)

  const load = useCallback(() => {
    apiGet('/api/admission-rights/?page_size=100')
      .then((d) => setRights(d.results || d))
      .catch(() => setRights([]))
  }, [])
  useEffect(load, [load])

  async function grant(e) {
    e.preventDefault()
    if (!form.user) {
      onMessage('Choose a staff member.')
      return
    }
    const body = { user: Number(form.user), note: form.note }
    if (form.expires_on) body.expires_on = form.expires_on
    const res = await apiWrite('/api/admission-rights/', body)
    onMessage(
      res.ok
        ? 'Admission rights granted.'
        : `Failed: ${JSON.stringify(res.data)}`,
    )
    if (res.ok) {
      setForm({ user: '', note: '', expires_on: '' })
      load()
    }
  }

  async function revoke(right) {
    const res = await apiWrite(`/api/admission-rights/${right.id}/`, {}, { method: 'DELETE' })
    onMessage(res.ok ? `Rights withdrawn from ${right.staff_name}.` : 'Could not withdraw.')
    load()
  }

  async function restore(right) {
    const res = await apiWrite(
      `/api/admission-rights/${right.id}/`, { active: true }, { method: 'PATCH' },
    )
    onMessage(res.ok ? `Rights restored to ${right.staff_name}.` : 'Could not restore.')
    load()
  }

  const active = rights.filter((r) => r.current)

  return (
    <div className="card">
      <div className="page-header" style={{ marginBottom: '0.4rem' }}>
        <h3 style={{ margin: 0 }}>
          Admission rights{active.length ? ` (${active.length} delegated)` : ''}
        </h3>
        <button onClick={() => setOpen((o) => !o)}>{open ? 'Close' : 'Manage'}</button>
      </div>
      <p className="muted">
        The admin can always admit learners. Delegate it to a head teacher, deputy or class
        teacher so they can open the admission form without the rest of the admin portal.
      </p>

      {open && (
        <>
          <form
            onSubmit={grant}
            style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center',
                     margin: '0.6rem 0' }}
          >
            <select
              value={form.user}
              onChange={(e) => setForm({ ...form, user: e.target.value })}
            >
              <option value="">Choose staff member…</option>
              {(supervisorChoices || []).map((c) => (
                <option key={c.id} value={c.id}>{c.name} ({c.kind})</option>
              ))}
            </select>
            <input
              placeholder="What for? e.g. Grade 1 intake 2027"
              value={form.note}
              onChange={(e) => setForm({ ...form, note: e.target.value })}
              style={{ padding: '0.4rem', minWidth: '16rem' }}
            />
            <label className="muted" style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
              Expires
              <input
                type="date"
                value={form.expires_on}
                onChange={(e) => setForm({ ...form, expires_on: e.target.value })}
              />
            </label>
            <button className="primary" type="submit">Grant</button>
          </form>

          {rights.length === 0 ? (
            <p className="muted">Nobody else can admit learners yet.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Staff</th><th>For</th><th>Expires</th><th>Status</th>
                  <th>Granted by</th><th></th>
                </tr>
              </thead>
              <tbody>
                {rights.map((r) => (
                  <tr key={r.id} style={r.current ? undefined : { opacity: 0.55 }}>
                    <td>{r.staff_name || r.username}</td>
                    <td className="muted">{r.note || '—'}</td>
                    <td className="muted">{r.expires_on || 'No expiry'}</td>
                    <td>
                      {r.current
                        ? <span className="badge online">Active</span>
                        : <span className="badge offline">
                            {r.active ? 'Expired' : 'Withdrawn'}
                          </span>}
                    </td>
                    <td className="muted">{r.granted_by_name || '—'}</td>
                    <td>
                      {r.active
                        ? <button onClick={() => revoke(r)}>Withdraw</button>
                        : <button onClick={() => restore(r)}>Restore</button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  )
}

const STAFF_COLUMN_SCOPES = [
  { value: 'TEACHING', label: 'Teaching staff only' },
  { value: 'NON_TEACHING', label: 'Non-teaching staff only' },
  { value: 'ALL', label: 'All staff' },
]

export default function Staff({ view }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [showInactive, setShowInactive] = useState(false)
  // panel: null | 'add' | {mode:'edit', kind, id}
  const [panel, setPanel] = useState(null)
  const [staffType, setStaffType] = useState('NON_TEACHING')
  const [form, setForm] = useState(EMPTY_SUPPORT)
  const [teacherForm, setTeacherForm] = useState(EMPTY_TEACHER)
  // Open column menu: {type:'field', id} | {type:'add', table} | null
  const [colMenu, setColMenu] = useState(null)

  const load = useCallback(() => {
    apiGet(`/api/school/staff/${showInactive ? '?include_inactive=true' : ''}`)
      .then(setData)
      .catch((e) => setError(e.message))
  }, [showInactive])
  useEffect(load, [load])

  // The sidebar's Staff "+" scopes the page; the Add form follows suit.
  useEffect(() => {
    if (view === 'TEACHING' || view === 'NON_TEACHING') setStaffType(view)
  }, [view])

  if (error) return <div className="error">{error}</div>
  if (!data) return <p className="muted">Loading staff…</p>

  const showTeaching = view !== 'NON_TEACHING'
  const showNonTeaching = view !== 'TEACHING'
  const editing = panel && panel.mode === 'edit' ? panel : null
  const editingUserId = editing?.userId ?? null

  const teachingFields = data.fields.filter((f) => ['ALL', 'TEACHING'].includes(f.applies_to))
  const nonTeachingFields = data.fields.filter((f) =>
    ['ALL', 'NON_TEACHING'].includes(f.applies_to),
  )
  const activeFields = staffType === 'TEACHING' ? teachingFields : nonTeachingFields

  const setField = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))
  const setTeacherField = (key) => (e) =>
    setTeacherForm((f) => ({ ...f, [key]: e.target.value }))
  const setExtra = (key) => (e) => {
    const value = e.target.value
    if (staffType === 'TEACHING') {
      setTeacherForm((f) => ({ ...f, extra: { ...f.extra, [key]: value } }))
    } else {
      setForm((f) => ({ ...f, extra: { ...f.extra, [key]: value } }))
    }
  }

  function openAdd() {
    setForm(EMPTY_SUPPORT)
    setTeacherForm(EMPTY_TEACHER)
    setMessage('')
    setPanel(panel === 'add' ? null : 'add')
  }

  function openEditTeacher(t) {
    const [first, ...rest] = (t.name || '').split(' ')
    setStaffType('TEACHING')
    setTeacherForm({
      ...EMPTY_TEACHER,
      first_name: first || '',
      last_name: rest.join(' '),
      tsc_number: t.tsc_number,
      employment_type: t.employment_type,
      rank: t.rank,
      phone: t.phone || '',
      supervisor: t.supervisor || '',
      extra: t.extra || {},
    })
    setMessage('')
    setPanel({ mode: 'edit', kind: 'TEACHING', id: t.id, name: t.name, userId: t.user_id })
  }

  function openEditSupport(s) {
    setStaffType('NON_TEACHING')
    setForm({
      full_name: s.full_name,
      category: s.category,
      title: s.title || '',
      phone: s.phone || '',
      employment_type: s.employment_type,
      supervisor: s.supervisor || '',
      extra: s.extra || {},
    })
    setMessage('')
    setPanel({ mode: 'edit', kind: 'NON_TEACHING', id: s.id, name: s.full_name, userId: s.user })
  }

  async function setActive(kind, id, active, name) {
    const path =
      kind === 'TEACHING' ? `/api/school/staff/teachers/${id}/` : `/api/support-staff/${id}/`
    const result = await apiWrite(path, { active }, { method: 'PATCH' })
    setMessage(
      result.ok
        ? `${name} ${active ? 'reactivated' : 'deactivated'}.`
        : `Could not update ${name}: ${JSON.stringify(result.data)}`,
    )
    if (result.ok) {
      setPanel(null)
      load()
    }
  }

  async function submitStaff(e) {
    e.preventDefault()
    const isTeaching = staffType === 'TEACHING'

    if (editing) {
      const path =
        editing.kind === 'TEACHING'
          ? `/api/school/staff/teachers/${editing.id}/`
          : `/api/support-staff/${editing.id}/`
      const body =
        editing.kind === 'TEACHING'
          ? {
              first_name: teacherForm.first_name,
              last_name: teacherForm.last_name,
              tsc_number: teacherForm.tsc_number,
              employment_type: teacherForm.employment_type,
              rank: teacherForm.rank,
              phone: teacherForm.phone,
              supervisor: teacherForm.supervisor === '' ? null : Number(teacherForm.supervisor),
              extra: teacherForm.extra,
            }
          : { ...form, supervisor: form.supervisor === '' ? null : Number(form.supervisor) }
      const result = await apiWrite(path, body, { method: 'PATCH' })
      setMessage(result.ok ? 'Staff record updated.' : `Failed: ${JSON.stringify(result.data)}`)
      if (result.ok) {
        setPanel(null)
        load()
      }
      return
    }

    if (isTeaching) {
      if (!teacherForm.first_name || !teacherForm.last_name || !teacherForm.tsc_number) {
        setMessage('Teaching staff need a first name, last name, and TSC/payroll number.')
        return
      }
      const result = await apiWrite('/api/school/staff/add-teacher/', {
        ...teacherForm,
        supervisor: teacherForm.supervisor === '' ? null : Number(teacherForm.supervisor),
      })
      if (result.ok) {
        const creds = result.data.generated_password
          ? ` Portal login: ${result.data.username} / ${result.data.generated_password} — share it now, it is not shown again.`
          : ` Portal login: ${result.data.username}.`
        setMessage(`${result.data.name} added as teaching staff.${creds}`)
        setTeacherForm(EMPTY_TEACHER)
        load()
      } else {
        setMessage(`Failed: ${JSON.stringify(result.data)}`)
      }
      return
    }

    if (!form.full_name) {
      setMessage('Enter the staff member’s name.')
      return
    }
    const result = await apiWrite('/api/support-staff/', {
      ...form,
      supervisor: form.supervisor === '' ? null : Number(form.supervisor),
    })
    setMessage(result.ok ? `${form.full_name} added.` : `Failed: ${JSON.stringify(result.data)}`)
    if (result.ok) {
      setForm(EMPTY_SUPPORT)
      load()
    }
  }

  const columns = columnApi('/api/staff-fields/', {
    onMessage: setMessage,
    onDone: () => { setColMenu(null); load() },
  })
  const addColumn = (label, applies_to) => columns.add(label, { applies_to })
  const renameColumn = (field, label) => columns.rename(field, label)
  const removeColumn = (field) => columns.remove(field)

  const toggleFieldMenu = (id) =>
    setColMenu((m) => (m?.type === 'field' && m.id === id ? null : { type: 'field', id }))
  const toggleAddMenu = (table) =>
    setColMenu((m) => (m?.type === 'add' && m.table === table ? null : { type: 'add', table }))

  // Category is a column, so rows are flat — ordered by category, then name.
  const orderOf = (groups) => Object.fromEntries(groups.map((g, i) => [g.key, i]))
  const teachingOrder = orderOf(data.teaching_groups)
  const nonTeachingOrder = orderOf(data.non_teaching_groups)

  const teachingRows = [...data.teaching].sort(
    (a, b) =>
      (teachingOrder[a.employment_type] ?? 99) - (teachingOrder[b.employment_type] ?? 99) ||
      a.name.localeCompare(b.name),
  )
  const nonTeachingRows = [...data.non_teaching].sort(
    (a, b) =>
      (nonTeachingOrder[a.category] ?? 99) - (nonTeachingOrder[b.category] ?? 99) ||
      a.full_name.localeCompare(b.full_name),
  )

  const heading =
    view === 'TEACHING'
      ? 'Teaching Staff'
      : view === 'NON_TEACHING'
        ? 'Non-teaching Staff'
        : 'Staff'

  return (
    <div>
      <div className="page-header">
        <h2>{heading}</h2>
        <button className="primary" onClick={openAdd}>
          {panel === 'add' ? 'Close' : '+ Add staff'}
        </button>
      </div>

      <p className="muted">
        {data.totals.teaching} teaching staff · {data.totals.non_teaching} non-teaching staff{' '}
        <label style={{ marginLeft: '0.5rem' }}>
          <input
            type="checkbox"
            checked={showInactive}
            onChange={(e) => setShowInactive(e.target.checked)}
          />{' '}
          show deactivated
        </label>
      </p>

      {/* Panels open at the top, above the register */}
      {(panel === 'add' || editing) && (
        <div className="card">
          <h3>{editing ? `Edit ${editing.name}` : 'Add staff'}</h3>
          <p>
            Staff type{' '}
            <select
              value={staffType}
              disabled={Boolean(editing)}
              onChange={(e) => { setStaffType(e.target.value); setMessage('') }}
            >
              <option value="TEACHING">Teaching staff</option>
              <option value="NON_TEACHING">Non-teaching staff</option>
            </select>
          </p>
          <form onSubmit={submitStaff} style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
            {staffType === 'TEACHING' ? (
              <>
                <input placeholder="First name" value={teacherForm.first_name}
                  onChange={setTeacherField('first_name')} style={{ padding: '0.4rem' }} />
                <input placeholder="Last name" value={teacherForm.last_name}
                  onChange={setTeacherField('last_name')} style={{ padding: '0.4rem' }} />
                <input placeholder="TSC / payroll no" value={teacherForm.tsc_number}
                  onChange={setTeacherField('tsc_number')} style={{ padding: '0.4rem' }} />
                <select value={teacherForm.employment_type} onChange={setTeacherField('employment_type')}>
                  {data.employment_choices.teaching.map((c) => (
                    <option key={c.value} value={c.value}>{c.label}</option>
                  ))}
                </select>
                <select value={teacherForm.rank} onChange={setTeacherField('rank')}>
                  {data.rank_choices.map((c) => (
                    <option key={c.value} value={c.value}>{c.label}</option>
                  ))}
                </select>
                <input placeholder="Phone 2547XXXXXXXX" value={teacherForm.phone}
                  onChange={setTeacherField('phone')} style={{ padding: '0.4rem' }} />
                <SupervisorSelect
                  value={teacherForm.supervisor}
                  onChange={setTeacherField('supervisor')}
                  choices={data.supervisor_choices}
                  excludeUserId={editing ? editingUserId : null}
                />
                {!editing && (
                  <>
                    <input placeholder="Username (optional)" value={teacherForm.username}
                      onChange={setTeacherField('username')} style={{ padding: '0.4rem' }} />
                    <input placeholder="Password (optional — generated if blank)" type="password"
                      value={teacherForm.password} onChange={setTeacherField('password')}
                      style={{ padding: '0.4rem', minWidth: '15rem' }} />
                  </>
                )}
              </>
            ) : (
              <>
                <input placeholder="Full name" value={form.full_name} onChange={setField('full_name')}
                  style={{ padding: '0.4rem' }} />
                <select value={form.category} onChange={setField('category')}>
                  {data.non_teaching_groups.map((g) => (
                    <option key={g.key} value={g.key}>{g.label}</option>
                  ))}
                </select>
                <input placeholder="Rank/title e.g. Head Cook" value={form.title}
                  onChange={setField('title')} style={{ padding: '0.4rem' }} />
                <input placeholder="Phone 2547XXXXXXXX" value={form.phone}
                  onChange={setField('phone')} style={{ padding: '0.4rem' }} />
                <select value={form.employment_type} onChange={setField('employment_type')}>
                  {data.employment_choices.non_teaching.map((c) => (
                    <option key={c.value} value={c.value}>{c.label}</option>
                  ))}
                </select>
                <SupervisorSelect
                  value={form.supervisor}
                  onChange={setField('supervisor')}
                  choices={data.supervisor_choices}
                  excludeUserId={editing ? editingUserId : null}
                />
              </>
            )}
            {activeFields.map((f) => (
              <input
                key={f.id}
                placeholder={f.label}
                value={
                  (staffType === 'TEACHING' ? teacherForm.extra : form.extra)?.[f.key] || ''
                }
                onChange={setExtra(f.key)}
                style={{ padding: '0.4rem' }}
              />
            ))}
            <button className="primary" type="submit">{editing ? 'Save changes' : 'Add'}</button>
            {editing && (
              <button type="button" onClick={() => setPanel(null)}>Cancel</button>
            )}
          </form>
          {message && <p className="muted">{message}</p>}
          {staffType === 'TEACHING' && !editing && (
            <p className="muted">
              Teaching staff get a portal login (role: teacher). Leave username/password blank to
              auto-generate them — the password is shown once after adding.
            </p>
          )}
        </div>
      )}

      <AdmissionRights
        supervisorChoices={data.supervisor_choices}
        onMessage={setMessage}
      />

      {showTeaching && (
        <div className="card">
          <h3>Teaching staff</h3>
          <table>
            <thead>
              <tr>
                <th>Name</th><th>TSC / Payroll No</th><th>Category</th><th>Rank</th>
                <th>Supervisor</th><th>Subjects</th>
                {teachingFields.map((f) => (
                  <ColumnHeader
                    key={f.id}
                    field={f}
                    open={colMenu?.type === 'field' && colMenu.id === f.id}
                    onToggle={() => toggleFieldMenu(f.id)}
                    onRename={(label) => renameColumn(f, label)}
                    onDelete={() => removeColumn(f)}
                  />
                ))}
                <th>Today</th><th></th>
                <AddColumnHeader
                  open={colMenu?.type === 'add' && colMenu.table === 'TEACHING'}
                  onToggle={() => toggleAddMenu('TEACHING')}
                  onAdd={addColumn}
                  scopes={STAFF_COLUMN_SCOPES}
                  defaultScope="TEACHING"
                />
              </tr>
            </thead>
            <tbody>
              {teachingRows.map((t) => (
                <tr key={t.id} style={t.active === false ? { opacity: 0.55 } : undefined}>
                  <td>
                    {t.name}
                    {t.active === false && <> <span className="badge offline">Deactivated</span></>}
                  </td>
                  <td>{t.tsc_number}</td>
                  <td>{t.employment_label}</td>
                  <td>{t.rank_label}</td>
                  <td className="muted">
                    {t.supervisor_name || <span className="badge queued">Not set</span>}
                  </td>
                  <td className="muted">{t.subjects.join(', ') || '—'}</td>
                  {teachingFields.map((f) => (
                    <td key={f.id}>{t.extra?.[f.key] || <span className="muted">—</span>}</td>
                  ))}
                  <td><PresenceBadge status={t.present_today} /></td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <button onClick={() => openEditTeacher(t)}>Edit</button>{' '}
                    <button
                      onClick={() => setActive('TEACHING', t.id, t.active === false, t.name)}
                    >
                      {t.active === false ? 'Reactivate' : 'Deactivate'}
                    </button>
                  </td>
                  <td />{/* spacer under the "+" column */}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showNonTeaching && (
        <div className="card">
          <h3>Non-teaching staff</h3>
          <table>
            <thead>
              <tr>
                <th>Name</th><th>Category</th><th>Rank / Title</th><th>Phone</th>
                <th>Employment</th><th>Supervisor</th>
                {nonTeachingFields.map((f) => (
                  <ColumnHeader
                    key={f.id}
                    field={f}
                    open={colMenu?.type === 'field' && colMenu.id === f.id}
                    onToggle={() => toggleFieldMenu(f.id)}
                    onRename={(label) => renameColumn(f, label)}
                    onDelete={() => removeColumn(f)}
                  />
                ))}
                <th></th>
                <AddColumnHeader
                  open={colMenu?.type === 'add' && colMenu.table === 'NON_TEACHING'}
                  onToggle={() => toggleAddMenu('NON_TEACHING')}
                  onAdd={addColumn}
                  scopes={STAFF_COLUMN_SCOPES}
                  defaultScope="NON_TEACHING"
                />
              </tr>
            </thead>
            <tbody>
              {nonTeachingRows.map((s) => (
                <tr key={s.id} style={!s.active ? { opacity: 0.55 } : undefined}>
                  <td>
                    {s.full_name}
                    {!s.active && <> <span className="badge offline">Deactivated</span></>}
                  </td>
                  <td>{s.category_label}</td>
                  <td>{s.title || '—'}</td>
                  <td>{s.phone ? <a href={`tel:${s.phone}`}>{s.phone}</a> : '—'}</td>
                  <td className="muted">{s.employment_label}</td>
                  <td className="muted">
                    {s.supervisor_name || <span className="badge queued">Not set</span>}
                  </td>
                  {nonTeachingFields.map((f) => (
                    <td key={f.id}>{s.extra?.[f.key] || <span className="muted">—</span>}</td>
                  ))}
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <button onClick={() => openEditSupport(s)}>Edit</button>{' '}
                    <button
                      onClick={() => setActive('NON_TEACHING', s.id, !s.active, s.full_name)}
                    >
                      {s.active ? 'Deactivate' : 'Reactivate'}
                    </button>
                  </td>
                  <td />{/* spacer under the "+" column */}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!panel && message && <p className="muted">{message}</p>}
    </div>
  )
}
