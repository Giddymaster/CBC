import { useCallback, useEffect, useState } from 'react'
import { apiGet, apiWrite } from './api.js'
import { gradeLabel } from './format.js'

/**
 * The Task Hub: every hat the school hands out — class teacher, games master,
 * HODs, TOD, cooks, security — in one list, each with its current holders and
 * one Assign flow: pick the task, pick the staff category, pick the person.
 * Leadership only (the office, head teacher or deputy); the server enforces it.
 */
export default function TaskHub() {
  const [catalog, setCatalog] = useState(null)
  const [duties, setDuties] = useState([])
  const [staff, setStaff] = useState(null)
  const [groups, setGroups] = useState([])
  const [message, setMessage] = useState('')
  // The open assign flow: { title, category } or { special: 'class_teacher' }
  const [assigning, setAssigning] = useState(null)
  const [pickStaff, setPickStaff] = useState('')
  const [pickClass, setPickClass] = useState('')
  const [custom, setCustom] = useState({ title: '', category: 'teaching' })

  const load = useCallback(() => {
    apiGet('/api/duties/catalog/').then(setCatalog).catch(() => {})
    apiGet('/api/duties/?page_size=300')
      .then((d) => setDuties(d.results || d)).catch(() => setDuties([]))
    apiGet('/api/school/staff/').then(setStaff).catch(() => {})
    apiGet('/api/class-groups/?page_size=200')
      .then((d) => setGroups(d.results || d)).catch(() => setGroups([]))
  }, [])
  useEffect(load, [load])

  if (!catalog || !staff) return <p className="muted">Loading the task hub…</p>

  const holders = (title) => duties.filter((d) => d.title === title)
  const teachingStaff = staff.teaching.filter((t) => t.user_id)
  const supportStaff = staff.non_teaching.filter((s) => s.user)

  const open = (title, category) => {
    setAssigning({ title, category })
    setPickStaff('')
    setPickClass('')
    setMessage('')
  }

  async function assignDuty() {
    if (!pickStaff) {
      setMessage('Pick the staff member.')
      return
    }
    const res = await apiWrite('/api/duties/', {
      user: Number(pickStaff),
      title: assigning.title,
    })
    if (res.ok) {
      setAssigning(null)
      setMessage(`${assigning.title} assigned.`)
      load()
    } else {
      setMessage(res.data?.detail || JSON.stringify(res.data))
    }
  }

  async function unassignDuty(duty) {
    if (!window.confirm(`Take ${duty.title} away from ${duty.staff_name}?`)) return
    await apiWrite(`/api/duties/${duty.id}/`, {}, { method: 'DELETE' })
    load()
  }

  async function assignClassTeacher() {
    if (!pickClass || !pickStaff) {
      setMessage('Pick the class and the teacher.')
      return
    }
    const res = await apiWrite(
      `/api/class-groups/${pickClass}/`,
      { class_teacher: Number(pickStaff) },
      { method: 'PATCH' },
    )
    if (res.ok) {
      setAssigning(null)
      setMessage('Class teacher seated.')
      load()
    } else {
      setMessage(res.data?.detail || JSON.stringify(res.data))
    }
  }

  async function unseatClassTeacher(group) {
    if (!window.confirm(`Unseat the class teacher of ${gradeLabel(group.grade)} ${group.stream || ''}?`)) return
    await apiWrite(`/api/class-groups/${group.id}/`, { class_teacher: null }, { method: 'PATCH' })
    load()
  }

  // For Class Teacher the picker offers TEACHERS; teacher_profile id, not user.
  const classLabelOf = (g) =>
    `${gradeLabel(g.grade)}${g.stream ? ` ${g.stream}` : ''}`

  const assignPanel = (isClassTeacher) => (
    <span className="taskhub-assign">
      {isClassTeacher && (
        <select value={pickClass} onChange={(e) => setPickClass(e.target.value)}>
          <option value="">Class…</option>
          {groups.map((g) => (
            <option key={g.id} value={g.id}>{classLabelOf(g)}</option>
          ))}
        </select>
      )}
      <select value={pickStaff} onChange={(e) => setPickStaff(e.target.value)}>
        <option value="">
          {assigning.category === 'teaching' ? 'Teacher…' : 'Staff member…'}
        </option>
        {(assigning.category === 'teaching' ? teachingStaff : supportStaff).map((p) =>
          isClassTeacher ? (
            <option key={p.id} value={p.id}>{p.name}</option>
          ) : (
            <option
              key={assigning.category === 'teaching' ? p.user_id : p.user}
              value={assigning.category === 'teaching' ? p.user_id : p.user}
            >
              {assigning.category === 'teaching' ? p.name : p.full_name}
            </option>
          ),
        )}
      </select>
      <button className="primary"
        onClick={isClassTeacher ? assignClassTeacher : assignDuty}>
        Assign
      </button>
      <button onClick={() => setAssigning(null)}>×</button>
    </span>
  )

  const taskRow = (title, category) => (
    <tr key={title}>
      <td style={{ whiteSpace: 'nowrap' }}><b>{title}</b></td>
      <td>
        {holders(title).length === 0 && <span className="muted">Unassigned</span>}
        {holders(title).map((d) => (
          <span key={d.id} className="stream-chip">
            {d.staff_name}
            <button type="button" title="Unassign" onClick={() => unassignDuty(d)}>×</button>
          </span>
        ))}
      </td>
      <td>
        {assigning?.title === title && !assigning?.special
          ? assignPanel(false)
          : <button onClick={() => open(title, category)}>Assign</button>}
      </td>
    </tr>
  )

  const seated = groups.filter((g) => g.class_teacher)

  return (
    <div>
      <div className="card">
        <h3>Class Teacher</h3>
        <p className="muted">
          Seated per class — this is who marks that class's attendance register.
        </p>
        <p style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', alignItems: 'center' }}>
          {seated.length === 0 && <span className="muted">No class teachers seated yet.</span>}
          {seated.map((g) => (
            <span key={g.id} className="stream-chip">
              {classLabelOf(g)} — {g.class_teacher_name || `#${g.class_teacher}`}
              <button type="button" title="Unseat" onClick={() => unseatClassTeacher(g)}>×</button>
            </span>
          ))}
        </p>
        {assigning?.special === 'class_teacher'
          ? assignPanel(true)
          : (
            <button className="primary"
              onClick={() => {
                setAssigning({ special: 'class_teacher', title: 'Class Teacher', category: 'teaching' })
                setPickStaff('')
                setPickClass('')
              }}>
              Assign a class teacher
            </button>
          )}
        {message && <p className="muted">{message}</p>}
      </div>

      <div className="card">
        <h3>Teaching tasks</h3>
        <table>
          <thead><tr><th>Task</th><th>Held by</th><th></th></tr></thead>
          <tbody>{catalog.teaching.map((t) => taskRow(t, 'teaching'))}</tbody>
        </table>
      </div>

      <div className="card">
        <h3>Non-teaching tasks</h3>
        <p className="muted">
          Assignment needs a portal login; staff without one are managed on the
          Staff page.
        </p>
        <table>
          <thead><tr><th>Task</th><th>Held by</th><th></th></tr></thead>
          <tbody>{catalog.non_teaching.map((t) => taskRow(t, 'non_teaching'))}</tbody>
        </table>
      </div>

      <div className="card">
        <h3>Custom task</h3>
        <p style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <input placeholder="Task name e.g. Assembly Coordinator" value={custom.title}
            onChange={(e) => setCustom({ ...custom, title: e.target.value })}
            style={{ padding: '0.4rem', minWidth: '15rem' }} />
          <select value={custom.category}
            onChange={(e) => setCustom({ ...custom, category: e.target.value })}>
            <option value="teaching">Teaching staff</option>
            <option value="non_teaching">Non-teaching staff</option>
          </select>
          {assigning?.title === custom.title && custom.title
            ? assignPanel(false)
            : (
              <button
                onClick={() => custom.title.trim() && open(custom.title.trim(), custom.category)}>
                Assign
              </button>
            )}
        </p>
      </div>
    </div>
  )
}
