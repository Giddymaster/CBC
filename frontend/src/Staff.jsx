import { useCallback, useEffect, useState } from 'react'
import { apiGet, apiWrite } from './api.js'
import { AddColumnHeader, ColumnHeader, columnApi, useAnchoredMenu } from './columns.jsx'
import { ALL_GRADES, gradeLabel } from './format.js'
import ImportCard from './ImportCard.jsx'

const PRESENT_LABEL = { P: 'Present', A: 'Absent', L: 'On leave' }
const PRESENT_BADGE = { P: 'online', A: 'offline', L: 'queued' }
const GENDER_OPTIONS = [
  { value: '', label: '—' },
  { value: 'M', label: 'Male' },
  { value: 'F', label: 'Female' },
  { value: 'O', label: 'Other' },
]

const EMPTY_SUPPORT = {
  full_name: '', category: 'KITCHEN', title: '', phone: '', gender: '',
  employment_type: 'BOM', supervisor: '', extra: {},
}
const EMPTY_TEACHER = {
  first_name: '', last_name: '', tsc_number: '', employment_type: 'TSC',
  rank: 'TEACHER', phase: '', phone: '', gender: '', username: '', password: '',
  supervisor: '', learning_areas: [], extra: {},
}

function PresenceBadge({ status }) {
  if (!status) return <span className="muted">Not marked</span>
  return <span className={`badge ${PRESENT_BADGE[status]}`}>{PRESENT_LABEL[status]}</span>
}

// ---- Excel-style cells: click the value, edit in place, Enter/blur saves ----

function CellText({ value, onSave }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  if (!editing) {
    return (
      <button type="button" className="cell-view" title="Click to edit"
        onClick={() => { setDraft(value || ''); setEditing(true) }}>
        {value || '—'}
      </button>
    )
  }
  return (
    <input
      className="cell-input" autoFocus value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => { setEditing(false); if (draft !== (value || '')) onSave(draft) }}
      onKeyDown={(e) => {
        if (e.key === 'Enter') e.currentTarget.blur()
        if (e.key === 'Escape') { setDraft(value || ''); e.currentTarget.blur() }
      }}
    />
  )
}

function CellSelect({ value, options, display, onSave }) {
  const [editing, setEditing] = useState(false)
  if (!editing) {
    return (
      <button type="button" className="cell-view" title="Click to edit"
        onClick={() => setEditing(true)}>
        {display || '—'}
      </button>
    )
  }
  return (
    <select className="cell-input" autoFocus value={value ?? ''}
      onChange={(e) => { setEditing(false); onSave(e.target.value) }}
      onBlur={() => setEditing(false)}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  )
}

// Subjects: a checkbox popover, because a teacher usually has more than one.
function CellSubjects({ ids, subjects, choices, onSave }) {
  const [open, setOpen] = useState(false)
  const [sel, setSel] = useState([])
  const [anchorRef, menuStyle] = useAnchoredMenu(open)
  const toggle = (id) =>
    setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))
  return (
    <>
      <button ref={anchorRef} type="button" className="cell-view" title="Click to edit"
        onClick={() => { setSel(ids || []); setOpen((o) => !o) }}>
        {subjects.join(', ') || '—'}
      </button>
      {open && (
        <div className="col-menu scrolly" style={menuStyle}>
          {choices.length === 0 && (
            <p className="muted" style={{ margin: 0 }}>
              No learning areas defined yet — add them under
              <b> School (Grades) → Learning areas</b>, then pick here.
            </p>
          )}
          {choices.map((c) => (
            <label key={c.id} className="subj-choice">
              <input type="checkbox" checked={sel.includes(c.id)}
                onChange={() => toggle(c.id)} />
              {c.name}
            </label>
          ))}
          <div style={{ display: 'flex', gap: '0.4rem' }}>
            {choices.length > 0 && (
              <button type="button" className="primary"
                onClick={() => { setOpen(false); onSave(sel) }}>Save</button>
            )}
            <button type="button" onClick={() => setOpen(false)}>
              {choices.length > 0 ? 'Cancel' : 'Close'}
            </button>
          </div>
        </div>
      )}
    </>
  )
}

// "This form is missing a field my school records" — define it on the spot:
// name it, choose free text or a fixed set of choices, and it becomes an input
// here plus a column on the register.
function NewFieldButton({ appliesTo, onCreated, onMessage }) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ label: '', field_type: 'TEXT', options: '' })

  async function create() {
    if (!form.label.trim()) {
      onMessage('Give the new field a name.')
      return
    }
    const options = form.options.split(',').map((s) => s.trim()).filter(Boolean)
    if (form.field_type === 'CHOICE' && options.length < 2) {
      onMessage('A choices field needs at least two options, comma-separated.')
      return
    }
    const res = await apiWrite('/api/staff-fields/', {
      label: form.label.trim(),
      applies_to: appliesTo,
      field_type: form.field_type,
      options: form.field_type === 'CHOICE' ? options : [],
    })
    if (res.ok) {
      onMessage(`Field "${form.label.trim()}" added — it is now a column on the register.`)
      setForm({ label: '', field_type: 'TEXT', options: '' })
      setOpen(false)
      onCreated()
    } else {
      onMessage(`Could not add the field: ${JSON.stringify(res.data)}`)
    }
  }

  if (!open) {
    return (
      <button type="button" className="grade-chip" onClick={() => setOpen(true)}>
        + New field
      </button>
    )
  }
  return (
    <span style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', alignItems: 'center',
                   border: '1px dashed #cbd5e0', borderRadius: '6px', padding: '0.4rem' }}>
      <input autoFocus placeholder="Field name e.g. NSSF number" value={form.label}
        onChange={(e) => setForm({ ...form, label: e.target.value })}
        style={{ padding: '0.35rem' }} />
      <select value={form.field_type}
        onChange={(e) => setForm({ ...form, field_type: e.target.value })}>
        <option value="TEXT">Free text</option>
        <option value="CHOICE">Choices</option>
      </select>
      {form.field_type === 'CHOICE' && (
        <input placeholder="Options, comma-separated" value={form.options}
          onChange={(e) => setForm({ ...form, options: e.target.value })}
          style={{ padding: '0.35rem', minWidth: '14rem' }} />
      )}
      <button type="button" className="primary" onClick={create}>Add field</button>
      <button type="button" onClick={() => setOpen(false)}>×</button>
    </span>
  )
}

// Everything the register holds about one person, in one card — plus the
// account actions (reset password, deactivate), so their results appear right
// here rather than somewhere below a long table.
function StaffProfile({ kind, row, fields, onClose, onChanged }) {
  const teaching = kind === 'TEACHING'
  const [creds, setCreds] = useState(null)
  const [note, setNote] = useState('')
  const userId = teaching ? row.user_id : row.user
  const isActive = teaching ? row.active !== false : Boolean(row.active)

  async function resetPassword() {
    if (!userId) {
      setNote('This person has no portal login to reset.')
      return
    }
    const displayName = teaching ? row.name : row.full_name
    if (!window.confirm(`Issue a new password for ${displayName}? Their current one stops working.`)) return
    const res = await apiWrite(`/api/school/staff/${userId}/reset-password/`, {})
    if (res.ok) {
      setCreds(res.data)
      setNote('')
    } else {
      setNote(res.data?.detail || 'Could not reset that password.')
    }
  }

  async function toggleActive() {
    const path = teaching
      ? `/api/school/staff/teachers/${row.id}/`
      : `/api/support-staff/${row.id}/`
    const res = await apiWrite(path, { active: !isActive }, { method: 'PATCH' })
    if (res.ok) {
      setNote('')
      onChanged?.()
    } else {
      setNote(res.data?.detail || 'Could not update this account.')
    }
  }

  const name = teaching ? row.name : row.full_name
  const initials = (name || '')
    .split(' ').filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join('')
  const items = (teaching
    ? [
        ['Username', row.username],
        ['TSC / Payroll no', row.tsc_number],
        ['Phone', row.phone],
        ['Gender', row.gender_label],
        ['Phase', row.phase_label],
        ['Category', row.employment_label],
        ['Rank', row.rank_label],
        ['Supervisor', row.supervisor_name],
        ['Subjects', row.subjects?.join(', ')],
        ['Today', PRESENT_LABEL[row.present_today] || 'Not marked'],
      ]
    : [
        ['Username', row.username],
        ['Category', row.category_label],
        ['Rank / title', row.title],
        ['Phone', row.phone],
        ['Gender', row.gender_label],
        ['Employment', row.employment_label],
        ['Supervisor', row.supervisor_name],
      ]
  ).concat(fields.map((f) => [f.label, row.extra?.[f.key]]))

  return (
    <div className="card profile-card">
      <div className="profile-head">
        <span className="avatar avatar-lg">{initials || '?'}</span>
        <div className="profile-headline">
          <h3>{name}</h3>
          <p className="profile-title">
            {teaching ? row.rank_label : row.title || row.category_label}
          </p>
          <p className="muted" style={{ margin: 0 }}>
            {isActive
              ? <span className="badge online">Active</span>
              : <span className="badge offline">Deactivated</span>}
          </p>
        </div>
        <span style={{ marginLeft: 'auto', display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
          <button onClick={resetPassword}>Reset password</button>
          <button onClick={toggleActive}>
            {isActive ? 'Deactivate' : 'Reactivate'}
          </button>
          <button onClick={onClose}>Close</button>
        </span>
      </div>

      {creds && (
        <div className="op-creds handover">
          <b>{creds.name}</b> — username <b>{creds.username}</b> · new password{' '}
          <b>{creds.generated_password}</b>
          <div className="muted">
            Hand both over now — they are not shown again. They will choose
            their own password at first sign-in.
          </div>
        </div>
      )}
      {note && <p className="error">{note}</p>}

      <div className="profile-grid">
        {items.map(([label, value]) => (
          <div className="profile-field" key={label}>
            <span className="profile-label">{label}</span>
            <span className="profile-value">{value || <span className="muted">—</span>}</span>
          </div>
        ))}
      </div>
    </div>
  )
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
  const [form, setForm] = useState({ user: '', note: '', expires_on: '', grades: [] })
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
    const body = { user: Number(form.user), note: form.note, grades: form.grades }
    if (form.expires_on) body.expires_on = form.expires_on
    const res = await apiWrite('/api/admission-rights/', body)
    onMessage(
      res.ok
        ? 'Admission rights granted.'
        : `Failed: ${JSON.stringify(res.data)}`,
    )
    if (res.ok) {
      setForm({ user: '', note: '', expires_on: '', grades: [] })
      load()
    }
  }

  const toggleGrade = (g) =>
    setForm((f) => ({
      ...f,
      grades: f.grades.includes(g)
        ? f.grades.filter((x) => x !== g)
        : [...f.grades, g].sort((a, b) => a - b),
    }))

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
            <div style={{ flexBasis: '100%' }}>
              <span className="muted">Grades they may admit into — none ticked = all grades:</span>{' '}
              {ALL_GRADES.map((g) => (
                <button
                  key={g}
                  type="button"
                  className={`grade-chip${form.grades.includes(g) ? ' on' : ''}`}
                  style={{ margin: '0.12rem 0.15rem' }}
                  onClick={() => toggleGrade(g)}
                >
                  {gradeLabel(g)}
                </button>
              ))}
            </div>
            <button className="primary" type="submit">Grant</button>
          </form>

          {rights.length === 0 ? (
            <p className="muted">Nobody else can admit learners yet.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Staff</th><th>For</th><th>Grades</th><th>Expires</th><th>Status</th>
                  <th>Granted by</th><th></th>
                </tr>
              </thead>
              <tbody>
                {rights.map((r) => (
                  <tr key={r.id} style={r.current ? undefined : { opacity: 0.55 }}>
                    <td>{r.staff_name || r.username}</td>
                    <td className="muted">{r.note || '—'}</td>
                    <td className="muted">
                      {(r.grades || []).length
                        ? r.grades.map(gradeLabel).join(', ')
                        : 'All grades'}
                    </td>
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
  // Open staff profile: {kind, id} | null — looked up fresh from data on render.
  const [profile, setProfile] = useState(null)

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

  // Inline cell edits — save one field, then reload the register.
  async function patchTeacher(id, body) {
    const res = await apiWrite(`/api/school/staff/teachers/${id}/`, body, { method: 'PATCH' })
    if (!res.ok) setMessage(`Could not save: ${JSON.stringify(res.data)}`)
    load()
  }
  async function patchSupport(id, body) {
    const res = await apiWrite(`/api/support-staff/${id}/`, body, { method: 'PATCH' })
    if (!res.ok) setMessage(`Could not save: ${JSON.stringify(res.data)}`)
    load()
  }
  // "Jane Wanjiru Kamau" → first name + the rest, mirroring how names entered.
  const splitName = (full) => {
    const [first, ...rest] = (full || '').trim().split(/\s+/)
    return { first_name: first || '', last_name: rest.join(' ') }
  }

  async function submitStaff(e) {
    e.preventDefault()
    const isTeaching = staffType === 'TEACHING'

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

  // Everyone who could be a supervisor, minus the person themselves.
  const supervisorOptions = (excludeUserId) => [
    { value: '', label: '— none —' },
    ...data.supervisor_choices
      .filter((c) => c.id !== excludeUserId)
      .map((c) => ({ value: String(c.id), label: `${c.name} (${c.kind})` })),
  ]
  const asSupervisor = (v) => ({ supervisor: v === '' ? null : Number(v) })

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
        <span style={{ display: 'flex', gap: '0.5rem' }}>
          <button onClick={() => { setPanel(panel === 'import' ? null : 'import'); setMessage('') }}>
            {panel === 'import' ? 'Close import' : 'Import CSV'}
          </button>
          <button className="primary" onClick={openAdd}>
            {panel === 'add' ? 'Close' : '+ Add staff'}
          </button>
        </span>
      </div>

      {panel === 'import' && (
        <ImportCard
          title="Import the staff room"
          blurb={
            'Teaching and non-teaching staff in one CSV — a Type column tells them '
            + 'apart. Teaching rows can carry Phase (Pre-Primary / Primary / JSS), '
            + 'Subjects (semicolon-separated, matching your learning areas) and a '
            + 'Class Teacher Of column like "G4 North". A row matching someone '
            + 'already on the register (by TSC number, or name for non-teaching) '
            + 'UPDATES that person — and reactivates them — instead of duplicating. '
            + 'New teaching staff get portal logins; passwords are shown once.'
          }
          endpoint="/api/school/staff/bulk/"
          templateName="staff_import_template.csv"
          commitNoun="staff"
          onDone={load}
          columns={[
            { key: 'name', label: 'Name' },
            { key: 'kind', label: 'Type' },
            {
              key: 'action', label: 'Action',
              render: (v) => (
                <span className={`badge ${v === 'Update' ? 'queued' : 'online'}`}>
                  {v}
                </span>
              ),
            },
            { key: 'detail', label: 'Rank / Title' },
            { key: 'subjects', label: 'Subjects' },
            {
              key: 'class_teacher_of', label: 'Class teacher of',
              render: (v) => {
                if (!v) return '—'
                const [g, s] = v.split('|')
                return `${gradeLabel(Number(g))}${s ? ` ${s}` : ''}`
              },
            },
          ]}
          extraResult={(result) =>
            result.logins?.length > 0 && (
              <div className="op-creds handover">
                <b>Portal logins — shown once, hand them over now.</b> Each person
                will be asked to choose their own password at first sign-in.
                <table>
                  <thead><tr><th>Name</th><th>Username</th><th>Password</th></tr></thead>
                  <tbody>
                    {result.logins.map((l) => (
                      <tr key={l.username}>
                        <td>{l.name}</td><td><b>{l.username}</b></td><td><b>{l.password}</b></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          }
        />
      )}

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
      {panel === 'add' && (
        <div className="card">
          <h3>Add staff</h3>
          <p>
            Staff type{' '}
            <select
              value={staffType}
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
                <input placeholder="Phone 07XX XXX XXX" value={teacherForm.phone}
                  onChange={setTeacherField('phone')} style={{ padding: '0.4rem' }} />
                <label className="muted" style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                  Gender
                  <select value={teacherForm.gender} onChange={setTeacherField('gender')}>
                    {GENDER_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                </label>
                <label className="muted" style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                  Phase
                  <select value={teacherForm.phase} onChange={setTeacherField('phase')}>
                    <option value="">—</option>
                    {(data.phase_choices || []).map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                </label>
                <SupervisorSelect
                  value={teacherForm.supervisor}
                  onChange={setTeacherField('supervisor')}
                  choices={data.supervisor_choices}
                  excludeUserId={null}
                />
                <input placeholder="Username (optional)" value={teacherForm.username}
                  onChange={setTeacherField('username')} style={{ padding: '0.4rem' }} />
                <input placeholder="Password (optional — generated if blank)" type="password"
                  value={teacherForm.password} onChange={setTeacherField('password')}
                  style={{ padding: '0.4rem', minWidth: '15rem' }} />
                <div className="subj-inline adm-wide">
                  <span className="adm-label">Subjects they teach</span>
                  <div className="subj-inline-list">
                    {(data.learning_area_choices || []).map((c) => (
                      <label key={c.id} className="subj-choice">
                        <input
                          type="checkbox"
                          checked={teacherForm.learning_areas.includes(c.id)}
                          onChange={() =>
                            setTeacherForm((f) => ({
                              ...f,
                              learning_areas: f.learning_areas.includes(c.id)
                                ? f.learning_areas.filter((x) => x !== c.id)
                                : [...f.learning_areas, c.id],
                            }))
                          }
                        />
                        {c.name}
                      </label>
                    ))}
                  </div>
                </div>
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
                <input placeholder="Phone 07XX XXX XXX" value={form.phone}
                  onChange={setField('phone')} style={{ padding: '0.4rem' }} />
                <label className="muted" style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                  Gender
                  <select value={form.gender} onChange={setField('gender')}>
                    {GENDER_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                </label>
                <select value={form.employment_type} onChange={setField('employment_type')}>
                  {data.employment_choices.non_teaching.map((c) => (
                    <option key={c.value} value={c.value}>{c.label}</option>
                  ))}
                </select>
                <SupervisorSelect
                  value={form.supervisor}
                  onChange={setField('supervisor')}
                  choices={data.supervisor_choices}
                  excludeUserId={null}
                />
              </>
            )}
            {activeFields.map((f) =>
              f.field_type === 'CHOICE' ? (
                <label key={f.id} className="muted"
                  style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                  {f.label}
                  <select
                    value={
                      (staffType === 'TEACHING' ? teacherForm.extra : form.extra)?.[f.key] || ''
                    }
                    onChange={setExtra(f.key)}
                  >
                    <option value="">—</option>
                    {(f.options || []).map((o) => <option key={o} value={o}>{o}</option>)}
                  </select>
                </label>
              ) : (
                <input
                  key={f.id}
                  placeholder={f.label}
                  value={
                    (staffType === 'TEACHING' ? teacherForm.extra : form.extra)?.[f.key] || ''
                  }
                  onChange={setExtra(f.key)}
                  style={{ padding: '0.4rem' }}
                />
              ),
            )}
            <NewFieldButton
              appliesTo={staffType}
              onCreated={() => load()}
              onMessage={setMessage}
            />
            <button className="primary" type="submit">Add</button>
          </form>
          {message && <p className="muted">{message}</p>}
          {staffType === 'TEACHING' && (
            <p className="muted">
              Teaching staff get a portal login (role: teacher). Leave username/password blank to
              auto-generate them — the password is shown once after adding.
            </p>
          )}
        </div>
      )}

      {profile && (() => {
        const row = profile.kind === 'TEACHING'
          ? data.teaching.find((t) => t.id === profile.id)
          : data.non_teaching.find((s) => s.id === profile.id)
        return row ? (
          <StaffProfile
            kind={profile.kind}
            row={row}
            fields={profile.kind === 'TEACHING' ? teachingFields : nonTeachingFields}
            onClose={() => setProfile(null)}
            onChanged={load}
          />
        ) : null
      })()}

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
                <th>Name</th><th>TSC / Payroll No</th><th>Phone</th><th>Gender</th>
                <th>Phase</th><th>Category</th><th>Rank</th><th>Supervisor</th>
                <th>Subjects</th>
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
                    <CellText value={t.name}
                      onSave={(v) => patchTeacher(t.id, splitName(v))} />
                    {t.active === false && <> <span className="badge offline">Deactivated</span></>}
                  </td>
                  <td>
                    <CellText value={t.tsc_number}
                      onSave={(v) => patchTeacher(t.id, { tsc_number: v })} />
                  </td>
                  <td>
                    <CellText value={t.phone}
                      onSave={(v) => patchTeacher(t.id, { phone: v })} />
                  </td>
                  <td>
                    <CellSelect value={t.gender} display={t.gender_label}
                      options={GENDER_OPTIONS}
                      onSave={(v) => patchTeacher(t.id, { gender: v })} />
                  </td>
                  <td>
                    <CellSelect value={t.phase} display={t.phase_label}
                      options={[{ value: '', label: '—' }, ...(data.phase_choices || [])]}
                      onSave={(v) => patchTeacher(t.id, { phase: v })} />
                  </td>
                  <td>
                    <CellSelect value={t.employment_type} display={t.employment_label}
                      options={data.employment_choices.teaching}
                      onSave={(v) => patchTeacher(t.id, { employment_type: v })} />
                  </td>
                  <td>
                    <CellSelect value={t.rank} display={t.rank_label}
                      options={data.rank_choices}
                      onSave={(v) => patchTeacher(t.id, { rank: v })} />
                  </td>
                  <td>
                    <CellSelect
                      value={t.supervisor == null ? '' : String(t.supervisor)}
                      display={t.supervisor_name || 'Not set'}
                      options={supervisorOptions(t.user_id)}
                      onSave={(v) => patchTeacher(t.id, asSupervisor(v))} />
                  </td>
                  <td>
                    <CellSubjects ids={t.learning_area_ids} subjects={t.subjects}
                      choices={data.learning_area_choices || []}
                      onSave={(ids) => patchTeacher(t.id, { learning_areas: ids })} />
                  </td>
                  {teachingFields.map((f) => (
                    <td key={f.id}>
                      {f.field_type === 'CHOICE' ? (
                        <CellSelect value={t.extra?.[f.key] || ''}
                          display={t.extra?.[f.key] || ''}
                          options={[{ value: '', label: '—' },
                            ...(f.options || []).map((o) => ({ value: o, label: o }))]}
                          onSave={(v) => patchTeacher(t.id, { extra: { [f.key]: v } })} />
                      ) : (
                        <CellText value={t.extra?.[f.key] || ''}
                          onSave={(v) => patchTeacher(t.id, { extra: { [f.key]: v } })} />
                      )}
                    </td>
                  ))}
                  <td><PresenceBadge status={t.present_today} /></td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <button onClick={() => {
                      setProfile({ kind: 'TEACHING', id: t.id })
                      window.scrollTo(0, 0)
                    }}>
                      Profile
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
                <th>Gender</th><th>Employment</th><th>Supervisor</th>
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
                    <CellText value={s.full_name}
                      onSave={(v) => patchSupport(s.id, { full_name: v })} />
                    {!s.active && <> <span className="badge offline">Deactivated</span></>}
                  </td>
                  <td>
                    <CellSelect value={s.category} display={s.category_label}
                      options={data.non_teaching_groups.map((g) => ({ value: g.key, label: g.label }))}
                      onSave={(v) => patchSupport(s.id, { category: v })} />
                  </td>
                  <td>
                    <CellText value={s.title}
                      onSave={(v) => patchSupport(s.id, { title: v })} />
                  </td>
                  <td>
                    <CellText value={s.phone}
                      onSave={(v) => patchSupport(s.id, { phone: v })} />
                  </td>
                  <td>
                    <CellSelect value={s.gender} display={s.gender_label}
                      options={GENDER_OPTIONS}
                      onSave={(v) => patchSupport(s.id, { gender: v })} />
                  </td>
                  <td>
                    <CellSelect value={s.employment_type} display={s.employment_label}
                      options={data.employment_choices.non_teaching}
                      onSave={(v) => patchSupport(s.id, { employment_type: v })} />
                  </td>
                  <td>
                    <CellSelect
                      value={s.supervisor == null ? '' : String(s.supervisor)}
                      display={s.supervisor_name || 'Not set'}
                      options={supervisorOptions(s.user)}
                      onSave={(v) => patchSupport(s.id, asSupervisor(v))} />
                  </td>
                  {nonTeachingFields.map((f) => (
                    <td key={f.id}>
                      {f.field_type === 'CHOICE' ? (
                        <CellSelect value={s.extra?.[f.key] || ''}
                          display={s.extra?.[f.key] || ''}
                          options={[{ value: '', label: '—' },
                            ...(f.options || []).map((o) => ({ value: o, label: o }))]}
                          onSave={(v) => patchSupport(s.id, { extra: { ...s.extra, [f.key]: v } })} />
                      ) : (
                        <CellText value={s.extra?.[f.key] || ''}
                          onSave={(v) => patchSupport(s.id, { extra: { ...s.extra, [f.key]: v } })} />
                      )}
                    </td>
                  ))}
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <button onClick={() => {
                      setProfile({ kind: 'NON_TEACHING', id: s.id })
                      window.scrollTo(0, 0)
                    }}>
                      Profile
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
