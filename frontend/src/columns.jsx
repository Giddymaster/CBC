import { useEffect, useRef, useState } from 'react'
import { apiWrite } from './api.js'

/** Position a menu against its trigger with position:fixed, so a scrolling
 * table (every register scrolls sideways now) cannot clip it. */
export function useAnchoredMenu(open, width = 240) {
  const anchorRef = useRef(null)
  const [style, setStyle] = useState(null)
  useEffect(() => {
    if (!open || !anchorRef.current) {
      setStyle(null)
      return
    }
    const r = anchorRef.current.getBoundingClientRect()
    setStyle({
      position: 'fixed',
      top: r.bottom + 4,
      left: Math.max(8, Math.min(r.left, window.innerWidth - width - 8)),
      width,
    })
  }, [open, width])
  return [anchorRef, style]
}

// Excel-style column header: left-click it to rename or delete the column.
export function ColumnHeader({ field, open, onToggle, onRename, onDelete }) {
  const [name, setName] = useState(field.label)
  useEffect(() => setName(field.label), [field.label])
  const [anchorRef, menuStyle] = useAnchoredMenu(open)

  return (
    <th className="col-head">
      <button ref={anchorRef} className="col-head-btn" onClick={onToggle}
        title="Edit or delete this column">
        {field.label} <span className="caret">▾</span>
      </button>
      {open && (
        <div className="col-menu" style={menuStyle}>
          <form
            onSubmit={(e) => { e.preventDefault(); onRename(name) }}
            style={{ display: 'flex', gap: '0.35rem' }}
          >
            <input value={name} onChange={(e) => setName(e.target.value)} style={{ padding: '0.3rem' }} />
            <button className="primary" type="submit">Save</button>
          </form>
          <button className="col-menu-danger" onClick={onDelete}>Delete column</button>
        </div>
      )}
    </th>
  )
}

// The trailing "+" header, like Excel's add-column affordance. Pass `scopes`
// when the column can apply to a subset (staff); omit it for a plain add.
export function AddColumnHeader({ open, onToggle, onAdd, scopes, defaultScope }) {
  const [label, setLabel] = useState('')
  const [scope, setScope] = useState(defaultScope)
  useEffect(() => setScope(defaultScope), [defaultScope])
  const [anchorRef, menuStyle] = useAnchoredMenu(open)

  return (
    <th className="col-head add-col">
      <button ref={anchorRef} className="col-head-btn plus" onClick={onToggle}
        title="Add a column">+</button>
      {open && (
        <div className="col-menu" style={menuStyle}>
          <form
            onSubmit={(e) => { e.preventDefault(); onAdd(label, scope); setLabel('') }}
            style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}
          >
            <input
              autoFocus
              placeholder="Column name e.g. National ID"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              style={{ padding: '0.3rem' }}
            />
            {scopes && (
              <select value={scope} onChange={(e) => setScope(e.target.value)}>
                {scopes.map((s) => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </select>
            )}
            <button className="primary" type="submit">Add column</button>
          </form>
        </div>
      )}
    </th>
  )
}

// Shared create/rename/delete calls against a custom-column endpoint.
export function columnApi(basePath, { onDone, onMessage }) {
  return {
    async add(label, extra = {}) {
      if (!label.trim()) {
        onMessage('Give the column a name.')
        return
      }
      const result = await apiWrite(basePath, { label, ...extra })
      onMessage(result.ok ? `Column "${label}" added.` : `Failed: ${JSON.stringify(result.data)}`)
      if (result.ok) onDone()
    },
    async rename(field, label) {
      if (!label.trim()) return
      const result = await apiWrite(`${basePath}${field.id}/`, { label }, { method: 'PATCH' })
      onMessage(result.ok ? `Column renamed to "${label}".` : 'Could not rename column.')
      if (result.ok) onDone()
    },
    async remove(field) {
      const result = await apiWrite(`${basePath}${field.id}/`, {}, { method: 'DELETE' })
      onMessage(result.ok ? `Column "${field.label}" deleted.` : 'Could not delete column.')
      onDone()
    },
  }
}
