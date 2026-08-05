import { useCallback, useEffect, useState } from 'react'
import { apiGet, apiUpload, apiWrite } from './api.js'
import { ALL_GRADES, gradeLabel } from './format.js'

const KINDS = [
  { value: 'DESIGN', label: 'Curriculum design' },
  { value: 'POLICY', label: 'Policy / circular' },
  { value: 'TEXTBOOK', label: 'Approved course book' },
  { value: 'GUIDE', label: 'Teacher guide' },
  { value: 'BANK', label: 'Assessment / question bank' },
  { value: 'OTHER', label: 'Other' },
]

// Highest standing first — the same order the backend ranks by.
const AUTHORITIES = [
  { value: 'MOE', label: 'Ministry of Education' },
  { value: 'KICD', label: 'KICD' },
  { value: 'KNEC', label: 'KNEC' },
  { value: 'TSC', label: 'TSC' },
  { value: 'COUNTY', label: 'County education office' },
  { value: 'SCHOOL', label: 'School document' },
  { value: 'OTHER', label: 'Other reference' },
]

function AuthorityBadge({ code, label }) {
  const strong = ['MOE', 'KICD', 'KNEC', 'TSC'].includes(code)
  return <span className={`badge ${strong ? 'online' : 'queued'}`}>{label || code}</span>
}

function MoeCanon() {
  const [canon, setCanon] = useState(null)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    apiGet('/api/moe/structure/').then(setCanon).catch(() => setCanon(null))
  }, [])
  if (!canon) return null

  return (
    <div className="card">
      <div className="page-header" style={{ marginBottom: '0.3rem' }}>
        <h3 style={{ margin: 0 }}>MoE structure — the authority</h3>
        <button onClick={() => setOpen((o) => !o)}>{open ? 'Close' : 'Show'}</button>
      </div>
      <p className="muted">
        Where any source disagrees — a brief, a textbook, a school handout, or a generated
        draft — this structure governs. Retrieval ranks sources in this order:{' '}
        {canon.authority_order.join(' › ')}.
      </p>

      {open && (
        <div className="profile-grid" style={{ marginTop: '0.6rem' }}>
          <div className="profile-field adm-wide">
            <span className="profile-label">Levels</span>
            <span className="profile-value">
              {canon.levels.map((l) => (
                <div key={l.key}>
                  <b>{l.name}</b> — {l.labels.join(', ')}
                </div>
              ))}
            </span>
          </div>
          <div className="profile-field adm-wide">
            <span className="profile-label">Senior School pathways (3)</span>
            <span className="profile-value">
              {canon.pathways.map((p) => (
                <div key={p.code}>
                  <b>{p.name}</b> — {p.tracks.join(' · ')}
                </div>
              ))}
            </span>
          </div>
          <div className="profile-field">
            <span className="profile-label">Competency levels</span>
            <span className="profile-value">
              {canon.competency_levels.map((c) => `${c.code} ${c.name}`).join(' · ')}
            </span>
          </div>
          <div className="profile-field">
            <span className="profile-label">Transitions</span>
            <span className="profile-value">
              {canon.transitions.map((t) => (
                <div key={t.key}>
                  {t.name}
                  {t.selects_pathway && <> — <b>pathway selected here</b></>}
                </div>
              ))}
            </span>
          </div>
        </div>
      )}
    </div>
  )
}

function Search({ areas }) {
  const [q, setQ] = useState('')
  const [area, setArea] = useState('')
  const [grade, setGrade] = useState('')
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)

  async function run(e) {
    e.preventDefault()
    if (!q.trim()) return
    setBusy(true)
    const params = new URLSearchParams({ q })
    if (area) params.set('learning_area', area)
    if (grade !== '') params.set('grade', grade)
    try {
      setResult(await apiGet(`/api/curriculum/search/?${params}`))
    } catch {
      setResult({ results: [], authority: {} })
    }
    setBusy(false)
  }

  return (
    <div className="card">
      <h3>Search the curriculum</h3>
      <form onSubmit={run} style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
        <input
          placeholder="e.g. separating mixtures, laboratory safety"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          style={{ padding: '0.4rem', flex: 1, minWidth: '18rem' }}
        />
        <select value={area} onChange={(e) => setArea(e.target.value)}>
          <option value="">All subjects</option>
          {areas.map((a) => (
            <option key={a.id} value={a.id}>{a.name}</option>
          ))}
        </select>
        <select value={grade} onChange={(e) => setGrade(e.target.value)}>
          <option value="">All grades</option>
          {ALL_GRADES.map((g) => (
            <option key={g} value={g}>{gradeLabel(g)}</option>
          ))}
        </select>
        <button className="primary" type="submit" disabled={busy}>
          {busy ? 'Searching…' : 'Search'}
        </button>
      </form>

      {result && result.results.length === 0 && (
        <p className="muted" style={{ marginTop: '0.6rem' }}>
          Nothing matched. Upload the relevant curriculum design below, or try
          different words — search is by keyword, not meaning.
        </p>
      )}

      {result?.authority?.mixed && (
        <p className="sync-note">
          Sources of differing standing matched this search. Where they disagree,{' '}
          <b>{result.authority.governing_label}</b> governs — its passages are listed first.
        </p>
      )}

      {result?.results.map((r) => (
        <div key={r.chunk_id} className="passage">
          <div className="passage-head">
            <AuthorityBadge code={r.authority} label={r.authority_label} />
            <b>{r.document}</b>
            {r.heading && <span className="muted">{r.heading}</span>}
            {r.national && <span className="badge queued">National</span>}
          </div>
          <p className="passage-text">{r.text}</p>
          <p className="muted">{r.citation}</p>
        </div>
      ))}
    </div>
  )
}

function UploadForm({ sources, areas, onDone, onMessage }) {
  const blank = {
    source: '', title: '', kind: 'DESIGN', learning_area: '', grades: [], text: '',
  }
  const [form, setForm] = useState(blank)
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))

  function toggleGrade(g) {
    setForm((f) => ({
      ...f,
      grades: f.grades.includes(g) ? f.grades.filter((x) => x !== g) : [...f.grades, g],
    }))
  }

  async function submit(e) {
    e.preventDefault()
    if (!form.source || !form.title.trim()) {
      onMessage('Choose a source and give the document a title.')
      return
    }
    if (!file && !form.text.trim()) {
      onMessage('Attach a file or paste the text — a document with neither cannot be indexed.')
      return
    }
    setBusy(true)
    let result
    if (file) {
      const body = new FormData()
      body.append('source', form.source)
      body.append('title', form.title)
      body.append('kind', form.kind)
      if (form.learning_area) body.append('learning_area', form.learning_area)
      form.grades.forEach((g) => body.append('grades', g))
      if (form.text.trim()) body.append('text', form.text)
      body.append('file', file)
      result = await apiUpload('/api/curriculum/documents/', body)
    } else {
      result = await apiWrite('/api/curriculum/documents/', {
        ...form,
        learning_area: form.learning_area || null,
      })
    }
    setBusy(false)
    if (result.ok) {
      const chunks = result.data?.chunk_count ?? 0
      onMessage(
        chunks
          ? `${result.data.title} added and indexed into ${chunks} passages.`
          : `${result.data.title} added, but no text could be extracted — paste the text to index it.`,
      )
      setForm(blank)
      setFile(null)
      onDone()
    } else {
      onMessage(`Failed: ${JSON.stringify(result.data)}`)
    }
  }

  return (
    <form onSubmit={submit} className="adm-grid" style={{ marginTop: '0.6rem' }}>
      <label className="adm-field">
        <span className="adm-label">Source *</span>
        <select value={form.source} onChange={set('source')}>
          <option value="">Choose…</option>
          {sources.map((s) => (
            <option key={s.id} value={s.id}>{s.name} — {s.authority_label}</option>
          ))}
        </select>
        <span className="adm-hint">Decides how much weight this document carries</span>
      </label>
      <label className="adm-field">
        <span className="adm-label">Title *</span>
        <input value={form.title} onChange={set('title')} />
      </label>
      <label className="adm-field">
        <span className="adm-label">Kind</span>
        <select value={form.kind} onChange={set('kind')}>
          {KINDS.map((k) => (
            <option key={k.value} value={k.value}>{k.label}</option>
          ))}
        </select>
      </label>
      <label className="adm-field">
        <span className="adm-label">Subject</span>
        <select value={form.learning_area} onChange={set('learning_area')}>
          <option value="">All subjects</option>
          {areas.map((a) => (
            <option key={a.id} value={a.id}>{a.name}</option>
          ))}
        </select>
      </label>
      <div className="adm-field adm-wide">
        <span className="adm-label">Grades</span>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.3rem' }}>
          {ALL_GRADES.map((g) => (
            <button
              type="button"
              key={g}
              onClick={() => toggleGrade(g)}
              className={form.grades.includes(g) ? 'grade-chip on' : 'grade-chip'}
            >
              {gradeLabel(g)}
            </button>
          ))}
        </div>
        <span className="adm-hint">None selected = applies to every grade</span>
      </div>
      <label className="adm-field adm-wide">
        <span className="adm-label">File</span>
        <input
          type="file"
          accept=".pdf,.txt,.md"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
        />
        <span className="adm-hint">
          .txt and .md index directly; PDFs need pypdf installed on the server
        </span>
      </label>
      <label className="adm-field adm-wide">
        <span className="adm-label">Or paste the text</span>
        <textarea rows="6" value={form.text} onChange={set('text')} />
        <span className="adm-hint">
          This is what gets indexed. Keep the document's own headings — they become
          the citations teachers see.
        </span>
      </label>
      <div className="adm-wide">
        <button className="primary" type="submit" disabled={busy}>
          {busy ? 'Indexing…' : 'Add to library'}
        </button>
      </div>
    </form>
  )
}

export default function Curriculum() {
  const [documents, setDocuments] = useState([])
  const [sources, setSources] = useState([])
  const [areas, setAreas] = useState([])
  const [message, setMessage] = useState('')
  const [adding, setAdding] = useState(false)
  const [me, setMe] = useState(null)

  const load = useCallback(() => {
    apiGet('/api/curriculum/documents/?page_size=200')
      .then((d) => setDocuments(d.results || d))
      .catch(() => setDocuments([]))
    apiGet('/api/curriculum/sources/?page_size=100')
      .then((d) => setSources(d.results || d))
      .catch(() => setSources([]))
    apiGet('/api/learning-areas/?page_size=100')
      .then((d) => setAreas(d.results || d))
      .catch(() => setAreas([]))
    apiGet('/api/me/').then(setMe).catch(() => setMe(null))
  }, [])
  useEffect(load, [load])

  const isAdmin = me?.role === 'ADMIN'

  async function reindex(doc) {
    const res = await apiWrite(`/api/curriculum/documents/${doc.id}/reindex/`, {})
    setMessage(
      res.ok ? `${doc.title} reindexed into ${res.data.chunks} passages.`
        : res.data?.detail || 'Could not reindex.',
    )
    load()
  }

  return (
    <div>
      <MoeCanon />
      <Search areas={areas} />

      <div className="card">
        <div className="page-header" style={{ marginBottom: '0.3rem' }}>
          <h3 style={{ margin: 0 }}>Curriculum library ({documents.length})</h3>
          {isAdmin && (
            <button className="primary" onClick={() => setAdding((a) => !a)}>
              {adding ? 'Close' : '+ Add document'}
            </button>
          )}
        </div>
        <p className="muted">
          What generated schemes of work are grounded in. National documents are shared
          by every school; your own uploads stay with this school.
        </p>

        {adding && (
          <UploadForm
            sources={sources}
            areas={areas}
            onDone={() => { setAdding(false); load() }}
            onMessage={setMessage}
          />
        )}
        {message && <p className="muted">{message}</p>}

        {documents.length === 0 ? (
          <p className="muted">
            The library is empty, so generated schemes are written without curriculum
            grounding and are labelled as such for the reviewer.
          </p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Title</th><th>Authority</th><th>Kind</th><th>Subject</th>
                <th>Grades</th><th>Passages</th><th>Scope</th>
                {isAdmin && <th></th>}
              </tr>
            </thead>
            <tbody>
              {documents.map((d) => (
                <tr key={d.id}>
                  <td>{d.title}</td>
                  <td><AuthorityBadge code={d.authority} label={d.authority_label} /></td>
                  <td className="muted">{d.kind_label}</td>
                  <td className="muted">{d.learning_area_name || 'All'}</td>
                  <td className="muted">
                    {d.grades?.length ? d.grades.map(gradeLabel).join(', ') : 'All'}
                  </td>
                  <td>
                    {d.chunk_count || <span className="badge offline">Not indexed</span>}
                  </td>
                  <td className="muted">{d.national ? 'National' : 'This school'}</td>
                  {isAdmin && (
                    <td><button onClick={() => reindex(d)}>Reindex</button></td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
