import { useCallback, useEffect, useState } from 'react'
import { apiGet, apiUpload } from './api.js'
import { ALL_GRADES, gradeLabel } from './format.js'

/**
 * The E-Learning library.
 *
 * Two faces, one page. For a learner or parent it is a shelf they browse and
 * search — video lessons that play inline, books and past papers to open,
 * links to work through — ranked by the same retrieval engine that grounds the
 * curriculum tools, so "photosynthesis grade 7" finds the right things. For the
 * office it is also where the shelf is stocked: paste a YouTube link, upload a
 * book, tag it with a grade and learning area.
 *
 * `canCurate` is passed from the shell (admin/office); everyone else gets the
 * shelf without the stocking controls. The server enforces both.
 */

const KIND_ICON = {
  VIDEO: '▶️', BOOK: '📚', NOTES: '📝', PAPER: '🧪', SIMULATION: '🔬', LINK: '🔗',
}
const KINDS = [
  { value: '', label: 'All kinds' },
  { value: 'VIDEO', label: 'Videos' },
  { value: 'BOOK', label: 'Books' },
  { value: 'NOTES', label: 'Notes' },
  { value: 'PAPER', label: 'Past papers' },
  { value: 'SIMULATION', label: 'Simulations' },
  { value: 'LINK', label: 'Web links' },
]

function VideoCard({ r, onPlay, playing }) {
  return (
    <div className="lr-card">
      {playing ? (
        <div className="lr-embed">
          <iframe
            src={`${r.youtube_embed}?autoplay=1`}
            title={r.title}
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
          />
        </div>
      ) : (
        <button className="lr-thumb" onClick={() => onPlay(r.id)} aria-label={`Play ${r.title}`}>
          {r.thumbnail && <img src={r.thumbnail} alt="" loading="lazy" />}
          <span className="lr-play">▶</span>
        </button>
      )}
      <ResourceMeta r={r} />
    </div>
  )
}

function ResourceMeta({ r }) {
  return (
    <div className="lr-meta">
      <div className="lr-title">
        <span aria-hidden="true">{KIND_ICON[r.kind] || '🔗'}</span> {r.title}
      </div>
      {r.description && <p className="lr-desc">{r.description}</p>}
      <div className="lr-tags">
        {r.learning_area && <span className="stream-chip">{r.learning_area}</span>}
        {(r.grades || []).map((g) => (
          <span key={g} className="lr-grade">{gradeLabel(g)}</span>
        ))}
        {r.national && <span className="lr-nat">National</span>}
        {r.source && <span className="lr-src">{r.source}</span>}
      </div>
    </div>
  )
}

function FileCard({ r }) {
  const open = r.file_url || r.url
  return (
    <div className="lr-card">
      <div className={`lr-filetop k-${r.kind.toLowerCase()}`}>
        <span className="lr-fileic">{KIND_ICON[r.kind] || '🔗'}</span>
        <span className="lr-kindlabel">{r.kind_label}</span>
      </div>
      <ResourceMeta r={r} />
      <div className="lr-actions">
        {open && <a className="btn-open" href={open} target="_blank" rel="noreferrer">Open</a>}
        {r.file_url && <a className="btn-open ghost" href={r.file_url} download>Download</a>}
      </div>
    </div>
  )
}

function AddResource({ areas, onAdded, isOperator }) {
  const empty = { kind: 'VIDEO', title: '', url: '', description: '', topic: '',
    learning_area: '', grades: [], national: false }
  const [form, setForm] = useState(empty)
  const [file, setFile] = useState(null)
  const [msg, setMsg] = useState('')
  const [open, setOpen] = useState(false)
  const linkKind = form.kind === 'VIDEO' || form.kind === 'LINK' || form.kind === 'SIMULATION'

  const toggleGrade = (g) =>
    setForm((f) => ({
      ...f,
      grades: f.grades.includes(g) ? f.grades.filter((x) => x !== g) : [...f.grades, g],
    }))

  async function submit() {
    if (!form.title.trim()) { setMsg('Give it a title.'); return }
    const body = new FormData()
    body.append('kind', form.kind)
    body.append('title', form.title.trim())
    body.append('description', form.description)
    body.append('topic', form.topic)
    if (form.url) body.append('url', form.url.trim())
    if (form.learning_area) body.append('learning_area', form.learning_area)
    form.grades.forEach((g) => body.append('grades', g))
    if (isOperator && form.national) body.append('school', '')
    if (file) body.append('file', file)
    const res = await apiUpload('/api/learning-resources/', body)
    if (res.ok) {
      setForm(empty); setFile(null); setOpen(false); setMsg('')
      onAdded()
    } else {
      setMsg(res.data?.detail || Object.values(res.data || {}).flat().join(' '))
    }
  }

  if (!open) {
    return (
      <button className="primary lr-add-btn" onClick={() => setOpen(true)}>
        + Add a resource
      </button>
    )
  }
  return (
    <div className="card lr-add">
      <h3>Add a learning resource</h3>
      <div className="lr-form">
        <label>Kind
          <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
            {KINDS.filter((k) => k.value).map((k) => (
              <option key={k.value} value={k.value}>{k.label}</option>
            ))}
          </select>
        </label>
        <label>Title
          <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })}
            placeholder="e.g. Photosynthesis explained" />
        </label>
        <label className="lr-wide">
          {form.kind === 'VIDEO' ? 'YouTube link' : 'Link (optional if you upload a file)'}
          <input value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })}
            placeholder={form.kind === 'VIDEO' ? 'https://youtu.be/…' : 'https://…'} />
        </label>
        {!linkKind && (
          <label className="lr-wide">Upload a file (book, notes, paper)
            <input type="file" onChange={(e) => setFile(e.target.files[0])} />
          </label>
        )}
        <label>Learning area
          <select value={form.learning_area}
            onChange={(e) => setForm({ ...form, learning_area: e.target.value })}>
            <option value="">Any</option>
            {areas.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        </label>
        <label className="lr-wide">Description
          <input value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            placeholder="One line on what it covers" />
        </label>
      </div>
      <div className="lr-grades">
        <span className="muted">Grades:</span>
        {ALL_GRADES.map((g) => (
          <button key={g} type="button"
            className={`lr-gpick${form.grades.includes(g) ? ' on' : ''}`}
            onClick={() => toggleGrade(g)}>{gradeLabel(g)}</button>
        ))}
      </div>
      {isOperator && (
        <label className="lr-nat-check">
          <input type="checkbox" checked={form.national}
            onChange={(e) => setForm({ ...form, national: e.target.checked })} />
          Publish to every school (national resource)
        </label>
      )}
      <div className="lr-form-actions">
        <button className="primary" onClick={submit}>Save</button>
        <button onClick={() => { setOpen(false); setMsg('') }}>Cancel</button>
        {msg && <span className="muted">{msg}</span>}
      </div>
    </div>
  )
}

export default function Learning({ canCurate = false, isOperator = false }) {
  const [items, setItems] = useState([])
  const [areas, setAreas] = useState([])
  const [q, setQ] = useState('')
  const [grade, setGrade] = useState('')
  const [kind, setKind] = useState('')
  const [area, setArea] = useState('')
  const [playing, setPlaying] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    setLoading(true)
    const params = new URLSearchParams()
    if (q.trim()) params.set('q', q.trim())
    if (grade) params.set('grade', grade)
    if (kind) params.set('kind', kind)
    if (area) params.set('learning_area', area)
    apiGet(`/api/learning-resources/search/?${params}`)
      .then((d) => setItems(d.results || []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false))
  }, [q, grade, kind, area])

  useEffect(() => {
    apiGet('/api/learning-areas/?page_size=100')
      .then((d) => setAreas(d.results || d)).catch(() => setAreas([]))
  }, [])
  useEffect(() => {
    const t = setTimeout(load, 250) // debounce the search box
    return () => clearTimeout(t)
  }, [load])

  return (
    <div>
      <div className="card lr-head">
        <div>
          <h3>E-Learning library</h3>
        </div>
        {canCurate && (
          <AddResource areas={areas} onAdded={load} isOperator={isOperator} />
        )}
      </div>

      <div className="card lr-filters">
        <input className="lr-search" placeholder="Search — e.g. photosynthesis, fractions…"
          value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          {KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
        </select>
        <select value={area} onChange={(e) => setArea(e.target.value)}>
          <option value="">All subjects</option>
          {areas.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
        <select value={grade} onChange={(e) => setGrade(e.target.value)}>
          <option value="">All grades</option>
          {ALL_GRADES.map((g) => <option key={g} value={g}>{gradeLabel(g)}</option>)}
        </select>
      </div>

      {loading && <p className="muted">Loading the library…</p>}
      {!loading && items.length === 0 && (
        <div className="card">
          <p className="muted">
            Nothing here yet{q || grade || kind || area ? ' for that search' : ''}.
            {canCurate && ' Add a video or a book to get the shelf started.'}
          </p>
        </div>
      )}

      <div className="lr-grid">
        {items.map((r) =>
          r.kind === 'VIDEO' && r.youtube_embed ? (
            <VideoCard key={r.id} r={r} playing={playing === r.id} onPlay={setPlaying} />
          ) : (
            <FileCard key={r.id} r={r} />
          ),
        )}
      </div>
    </div>
  )
}
