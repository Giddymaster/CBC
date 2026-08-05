import { useCallback, useEffect, useState } from 'react'
import { apiGet, apiWrite } from './api.js'

const STATUS_BADGE = { IN_STOCK: 'online', LOW: 'queued', DEPLETED: 'offline' }
const STATUS_LABEL = { IN_STOCK: 'In stock', LOW: 'Running low', DEPLETED: 'Depleted' }

export const ADD_CATEGORY = '__add_category__'

const EMPTY_FACILITY = {
  name: '', category: '', location: '', capacity: '', notes: '',
}
const EMPTY_SUPPLY = { item: '', unit: 'pcs', quantity: '0', reorder_level: '0' }

export function StockBadge({ status }) {
  return <span className={`badge ${STATUS_BADGE[status]}`}>{STATUS_LABEL[status]}</span>
}

function FacilityDetail({ facilityId, onBack, onChanged }) {
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [staffOptions, setStaffOptions] = useState({ teaching: [], non_teaching: [] })
  const [supplyForm, setSupplyForm] = useState(EMPTY_SUPPLY)
  const [assignForm, setAssignForm] = useState({ staff: '', position: '' })
  const [editingSupply, setEditingSupply] = useState(null)

  const load = useCallback(() => {
    apiGet(`/api/facilities/${facilityId}/`).then(setDetail).catch((e) => setError(e.message))
  }, [facilityId])
  useEffect(load, [load])

  useEffect(() => {
    apiGet('/api/school/staff/')
      .then((d) => setStaffOptions({ teaching: d.teaching, non_teaching: d.non_teaching }))
      .catch(() => {})
  }, [])

  if (error) return <div className="error">{error}</div>
  if (!detail) return <p className="muted">Loading facility…</p>

  const supplies = detail.supplies || []
  const depleted = supplies.filter((s) => s.status === 'DEPLETED')
  const low = supplies.filter((s) => s.status === 'LOW')

  async function addSupply(e) {
    e.preventDefault()
    if (!supplyForm.item.trim()) {
      setMessage('Name the item first.')
      return
    }
    const result = await apiWrite('/api/supplies/', { ...supplyForm, facility: facilityId })
    setMessage(result.ok ? `${supplyForm.item} added.` : `Failed: ${JSON.stringify(result.data)}`)
    if (result.ok) {
      setSupplyForm(EMPTY_SUPPLY)
      load()
      onChanged()
    }
  }

  async function saveQuantity(supply, quantity) {
    const result = await apiWrite(
      `/api/supplies/${supply.id}/`,
      { quantity, last_restocked: new Date().toISOString().slice(0, 10) },
      { method: 'PATCH' },
    )
    setMessage(result.ok ? `${supply.item} updated.` : 'Could not update stock.')
    setEditingSupply(null)
    if (result.ok) {
      load()
      onChanged()
    }
  }

  async function removeSupply(supply) {
    const result = await apiWrite(`/api/supplies/${supply.id}/`, {}, { method: 'DELETE' })
    setMessage(result.ok ? `${supply.item} removed.` : 'Could not remove item.')
    load()
    onChanged()
  }

  async function assignStaff(e) {
    e.preventDefault()
    if (!assignForm.staff || !assignForm.position.trim()) {
      setMessage('Pick a staff member and give their position here.')
      return
    }
    const [kind, id] = assignForm.staff.split(':')
    const body = {
      facility: facilityId,
      position: assignForm.position,
      ...(kind === 'T' ? { teacher: Number(id) } : { support_staff: Number(id) }),
    }
    const result = await apiWrite('/api/facility-assignments/', body)
    setMessage(result.ok ? 'Staff posted to this facility.' : `Failed: ${JSON.stringify(result.data)}`)
    if (result.ok) {
      setAssignForm({ staff: '', position: '' })
      load()
      onChanged()
    }
  }

  async function removeAssignment(a) {
    const result = await apiWrite(`/api/facility-assignments/${a.id}/`, {}, { method: 'DELETE' })
    setMessage(result.ok ? `${a.staff_name} removed from this facility.` : 'Could not remove.')
    load()
    onChanged()
  }

  return (
    <div>
      <p>
        <button onClick={onBack}>← All facilities</button>{' '}
        <b>{detail.name}</b>{' '}
        <span className="muted">
          {detail.type_label}
          {detail.location ? ` · ${detail.location}` : ''}
          {detail.capacity ? ` · capacity ${detail.capacity}` : ''}
        </span>
      </p>
      {(depleted.length > 0 || low.length > 0) && (
        <p>
          {depleted.length > 0 && (
            <span className="badge offline">{depleted.length} depleted</span>
          )}{' '}
          {low.length > 0 && <span className="badge queued">{low.length} running low</span>}{' '}
          <span className="muted">
            {[...depleted, ...low].map((s) => s.item).join(', ')}
          </span>
        </p>
      )}
      {message && <p className="muted">{message}</p>}

      <div className="card">
        <h3>Staff & positions</h3>
        {detail.assignments.length === 0 && <p className="muted">Nobody posted here yet.</p>}
        {detail.assignments.length > 0 && (
          <table>
            <thead>
              <tr><th>Name</th><th>Position here</th><th>Staff type</th><th></th></tr>
            </thead>
            <tbody>
              {detail.assignments.map((a) => (
                <tr key={a.id}>
                  <td>{a.staff_name}</td>
                  <td>{a.position}</td>
                  <td className="muted">
                    {a.staff_kind === 'TEACHING' ? 'Teaching' : 'Non-teaching'}
                  </td>
                  <td><button onClick={() => removeAssignment(a)}>Remove</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <form onSubmit={assignStaff} style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center', marginTop: '0.5rem' }}>
          <select value={assignForm.staff} onChange={(e) => setAssignForm((f) => ({ ...f, staff: e.target.value }))}>
            <option value="">Post a staff member…</option>
            <optgroup label="Teaching">
              {staffOptions.teaching.map((t) => (
                <option key={`T${t.id}`} value={`T:${t.id}`}>{t.name}</option>
              ))}
            </optgroup>
            <optgroup label="Non-teaching">
              {staffOptions.non_teaching.map((s) => (
                <option key={`S${s.id}`} value={`S:${s.id}`}>{s.full_name}</option>
              ))}
            </optgroup>
          </select>
          <input
            placeholder="Position here e.g. Head Cook"
            value={assignForm.position}
            onChange={(e) => setAssignForm((f) => ({ ...f, position: e.target.value }))}
            style={{ padding: '0.4rem' }}
          />
          <button className="primary" type="submit">Post to facility</button>
        </form>
      </div>

      <div className="card">
        <h3>Supplies</h3>
        {supplies.length === 0 && <p className="muted">No supplies recorded.</p>}
        {supplies.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>Item</th><th>Quantity</th><th>Unit</th><th>Reorder at</th>
                <th>Status</th><th>Last restocked</th><th></th>
              </tr>
            </thead>
            <tbody>
              {supplies.map((s) => (
                <tr key={s.id}>
                  <td>{s.item}</td>
                  <td>
                    {editingSupply === s.id ? (
                      <input
                        autoFocus
                        type="number"
                        defaultValue={s.quantity}
                        style={{ width: '6rem', padding: '0.25rem' }}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') saveQuantity(s, e.target.value)
                          if (e.key === 'Escape') setEditingSupply(null)
                        }}
                        onBlur={(e) => saveQuantity(s, e.target.value)}
                      />
                    ) : (
                      <button className="clear-grade" onClick={() => setEditingSupply(s.id)}>
                        {Number(s.quantity)}
                      </button>
                    )}
                  </td>
                  <td className="muted">{s.unit}</td>
                  <td className="muted">{Number(s.reorder_level)}</td>
                  <td><StockBadge status={s.status} /></td>
                  <td className="muted">{s.last_restocked || '—'}</td>
                  <td><button onClick={() => removeSupply(s)}>Remove</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <form onSubmit={addSupply} style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center', marginTop: '0.5rem' }}>
          <input placeholder="Item e.g. Maize flour" value={supplyForm.item}
            onChange={(e) => setSupplyForm((f) => ({ ...f, item: e.target.value }))}
            style={{ padding: '0.4rem' }} />
          <input placeholder="Qty" type="number" value={supplyForm.quantity}
            onChange={(e) => setSupplyForm((f) => ({ ...f, quantity: e.target.value }))}
            style={{ padding: '0.4rem', width: '6rem' }} />
          <input placeholder="Unit" value={supplyForm.unit}
            onChange={(e) => setSupplyForm((f) => ({ ...f, unit: e.target.value }))}
            style={{ padding: '0.4rem', width: '6rem' }} />
          <input placeholder="Reorder at" type="number" value={supplyForm.reorder_level}
            onChange={(e) => setSupplyForm((f) => ({ ...f, reorder_level: e.target.value }))}
            style={{ padding: '0.4rem', width: '7rem' }} />
          <button className="primary" type="submit">Add supply</button>
        </form>
        <p className="muted">
          Click a quantity to edit it — anything at or below its reorder level shows as running
          low, and zero shows as depleted.
        </p>
      </div>
    </div>
  )
}

export default function Facilities({ facility, onNavRefresh }) {
  const [list, setList] = useState([])
  const [categories, setCategories] = useState([])
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [selected, setSelected] = useState(null)
  const [panel, setPanel] = useState(null) // 'facility' | 'category' | null
  const [form, setForm] = useState(EMPTY_FACILITY)
  const [categoryName, setCategoryName] = useState('')
  const [sections, setSections] = useState([])
  const [renaming, setRenaming] = useState({}) // id -> new name

  const load = useCallback(() => {
    apiGet('/api/facilities/?page_size=200')
      .then((d) => setList(d.results || d))
      .catch((e) => setError(e.message))
    apiGet('/api/facility-categories/?page_size=100')
      .then((d) => setCategories(d.results || d))
      .catch(() => setCategories([]))
    apiGet('/api/nav-sections/?page_size=50')
      .then((d) => setSections(d.results || d))
      .catch(() => setSections([]))
  }, [])
  useEffect(load, [load])

  // The sidebar can open a category, a facility, or the "add category" form.
  // Managing categories belongs to the All-facilities view, so any open panel
  // closes when you drill into one category.
  useEffect(() => {
    setSelected(null)
    setPanel(facility === ADD_CATEGORY ? 'category' : null)
  }, [facility])

  if (error) return <div className="error">{error}</div>

  if (selected) {
    return (
      <FacilityDetail
        facilityId={selected}
        onBack={() => setSelected(null)}
        onChanged={load}
      />
    )
  }

  const categoryScope =
    facility && facility !== ADD_CATEGORY ? Number(facility) : null
  const visible = categoryScope
    ? list.filter((f) => f.category === categoryScope)
    : list

  async function addFacility(e) {
    e.preventDefault()
    if (!form.name.trim()) {
      setMessage('Give the facility a name.')
      return
    }
    const category = form.category || categoryScope || categories[0]?.id
    if (!category) {
      setMessage('Add a category first — every facility belongs to one.')
      return
    }
    const body = {
      ...form,
      category,
      capacity: form.capacity === '' ? null : Number(form.capacity),
    }
    const result = await apiWrite('/api/facilities/', body)
    setMessage(result.ok ? `${form.name} added.` : `Failed: ${JSON.stringify(result.data)}`)
    if (result.ok) {
      setForm(EMPTY_FACILITY)
      setPanel(null)
      load()
      onNavRefresh?.()
    }
  }

  async function addCategory(e) {
    e.preventDefault()
    if (!categoryName.trim()) {
      setMessage('Give the category a name.')
      return
    }
    const result = await apiWrite('/api/facility-categories/', {
      name: categoryName,
      order: categories.length,
    })
    setMessage(result.ok ? `Category "${categoryName}" added.` : `Failed: ${JSON.stringify(result.data)}`)
    if (result.ok) {
      setCategoryName('')
      load()
      onNavRefresh?.()
    }
  }

  async function renameCategory(cat) {
    const name = renaming[cat.id]
    if (!name || !name.trim()) return
    const result = await apiWrite(`/api/facility-categories/${cat.id}/`, { name }, { method: 'PATCH' })
    setMessage(result.ok ? `Renamed to "${name}".` : 'Could not rename category.')
    if (result.ok) {
      setRenaming((r) => ({ ...r, [cat.id]: undefined }))
      load()
      onNavRefresh?.()
    }
  }

  async function moveCategory(cat, sectionId) {
    const result = await apiWrite(
      `/api/facility-categories/${cat.id}/`,
      { section: sectionId === '' ? null : Number(sectionId) },
      { method: 'PATCH' },
    )
    setMessage(result.ok ? `${cat.name} moved.` : 'Could not move category.')
    if (result.ok) {
      load()
      onNavRefresh?.()
    }
  }

  async function deleteCategory(cat) {
    const result = await apiWrite(`/api/facility-categories/${cat.id}/`, {}, { method: 'DELETE' })
    setMessage(
      result.ok
        ? `Category "${cat.name}" deleted.`
        : result.data?.detail || 'Move its facilities out before deleting this category.',
    )
    load()
    onNavRefresh?.()
  }

  const byCategory = {}
  for (const f of visible) (byCategory[f.category_name] = byCategory[f.category_name] || []).push(f)

  return (
    <div>
      <div className="page-header">
        <h2>{categoryScope ? categories.find((c) => c.id === categoryScope)?.name || 'Facilities' : 'Facilities'}</h2>
        <span style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          {/* Categories are managed from the All-facilities view only */}
          {!categoryScope && (
            <button onClick={() => { setPanel(panel === 'category' ? null : 'category'); setMessage('') }}>
              {panel === 'category' ? 'Close' : '+ Add category'}
            </button>
          )}
          <button className="primary" onClick={() => { setPanel(panel === 'facility' ? null : 'facility'); setMessage('') }}>
            {panel === 'facility' ? 'Close' : '+ Add facility'}
          </button>
        </span>
      </div>
      <p className="muted">
        {visible.length} facilities ·{' '}
        {visible.reduce((n, f) => n + (f.supply_summary?.depleted || 0), 0)} depleted items ·{' '}
        {visible.reduce((n, f) => n + (f.supply_summary?.low || 0), 0)} running low
      </p>

      {panel === 'category' && !categoryScope && (
        <div className="card">
          <h3>Categories</h3>
          <form onSubmit={addCategory} style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
            <input placeholder="New category e.g. Swimming Pool" value={categoryName}
              onChange={(e) => setCategoryName(e.target.value)} style={{ padding: '0.4rem' }} />
            <button className="primary" type="submit">Add category</button>
          </form>
          <table>
            <thead>
              <tr>
                <th>Category</th><th>Facilities</th><th>Sidebar section</th>
                <th>Rename</th><th></th>
              </tr>
            </thead>
            <tbody>
              {categories.map((c) => (
                <tr key={c.id}>
                  <td>{c.name}</td>
                  <td>{c.facility_count}</td>
                  <td>
                    <select
                      value={c.section ?? ''}
                      onChange={(e) => moveCategory(c, e.target.value)}
                    >
                      <option value="">Facilities (default)</option>
                      {sections.map((s) => (
                        <option key={s.id} value={s.id}>{s.name}</option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <input
                      value={renaming[c.id] ?? c.name}
                      onChange={(e) => setRenaming((r) => ({ ...r, [c.id]: e.target.value }))}
                      style={{ padding: '0.25rem', width: '11rem' }}
                    />{' '}
                    <button onClick={() => renameCategory(c)}>Save</button>
                  </td>
                  <td>
                    <button onClick={() => deleteCategory(c)} disabled={c.facility_count > 0}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {panel === 'facility' && (
        <div className="card">
          <h3>Add facility</h3>
          <form onSubmit={addFacility} style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
            <input placeholder="Name e.g. School Bus KBZ 112A" value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              style={{ padding: '0.4rem' }} />
            <select value={form.category || categoryScope || ''}
              onChange={(e) => setForm((f) => ({ ...f, category: Number(e.target.value) }))}>
              <option value="">Category…</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
            <input placeholder="Location" value={form.location}
              onChange={(e) => setForm((f) => ({ ...f, location: e.target.value }))}
              style={{ padding: '0.4rem' }} />
            <input placeholder="Capacity" type="number" value={form.capacity}
              onChange={(e) => setForm((f) => ({ ...f, capacity: e.target.value }))}
              style={{ padding: '0.4rem', width: '7rem' }} />
            <button className="primary" type="submit">Add</button>
          </form>
        </div>
      )}
      {message && <p className="muted">{message}</p>}

      {Object.entries(byCategory).map(([type, items]) => (
        <div className="card" key={type}>
          <h3>{type}</h3>
          <table>
            <thead>
              <tr>
                <th>Facility</th><th>Location</th><th>Capacity</th><th>Staff</th>
                <th>Supplies</th><th>Stock alerts</th><th></th>
              </tr>
            </thead>
            <tbody>
              {items.map((f) => (
                <tr key={f.id}>
                  <td>{f.name}</td>
                  <td className="muted">{f.location || '—'}</td>
                  <td>{f.capacity ?? '—'}</td>
                  <td>{f.staff_count}</td>
                  <td>{f.supply_summary.total}</td>
                  <td>
                    {f.supply_summary.depleted > 0 && (
                      <span className="badge offline">{f.supply_summary.depleted} depleted</span>
                    )}{' '}
                    {f.supply_summary.low > 0 && (
                      <span className="badge queued">{f.supply_summary.low} low</span>
                    )}
                    {f.supply_summary.depleted === 0 && f.supply_summary.low === 0 && (
                      <span className="badge online">OK</span>
                    )}
                  </td>
                  <td><button onClick={() => setSelected(f.id)}>Open</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  )
}
