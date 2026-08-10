import { useCallback, useEffect, useRef, useState } from 'react'
import { apiGet, apiUpload, apiWrite } from './api.js'

/**
 * School Profile — the school's own record of itself.
 *
 * Four things live here because all four are things the school decides and
 * everything else reads: the number a parent rings, the crest at the top of a
 * report card, the headings on the fee note, and the paperwork an inspector
 * asks for. Registration facts (the MoE code, the county, the paybill prefix)
 * are shown but not editable — those belong to the operator, because a school
 * renaming its own code would break the register it is registered in.
 */

function Field({ label, value, onChange, placeholder, disabled, type = 'text' }) {
  return (
    <label className="sp-field">
      <span>{label}</span>
      <input
        type={type}
        value={value || ''}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  )
}

function Facts({ profile }) {
  const rows = [
    ['School', profile.name],
    ['MoE code', profile.code],
    ['KEMIS code', profile.kemis_code],
    ['County', [profile.county, profile.subcounty, profile.ward].filter(Boolean).join(' · ')],
    ['Paybill prefix', profile.paybill_account_prefix],
  ].filter(([, v]) => v)
  return (
    <div className="sp-facts">
      {rows.map(([label, value]) => (
        <div key={label}>
          <small>{label}</small>
          <b>{value}</b>
        </div>
      ))}
    </div>
  )
}

function VoteHeads({ heads, canEdit, onChange }) {
  const [adding, setAdding] = useState('')
  const [editing, setEditing] = useState(null)

  const rename = (index, name) => {
    const text = name.trim()
    setEditing(null)
    if (!text || heads[index] === text) return
    onChange(heads.map((h, i) => (i === index ? text : h)))
  }

  return (
    <div className="card">
      <h3>Fee note headings</h3>
      <p className="muted">
        The columns of your fee structure, in the order they print. Removing one
        here does not touch a term already priced under it — that money still
        shows on the fee grid.
      </p>
      <div className="sp-heads">
        {heads.map((head, index) =>
          editing === index ? (
            <input
              key={head}
              className="sp-head-edit"
              autoFocus
              defaultValue={head}
              onBlur={(e) => rename(index, e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') rename(index, e.target.value)
                if (e.key === 'Escape') setEditing(null)
              }}
            />
          ) : (
            <span key={head} className="stream-chip">
              <button
                type="button"
                className="sp-head-name"
                title={canEdit ? 'Rename' : ''}
                onClick={() => canEdit && setEditing(index)}
              >
                {head}
              </button>
              {canEdit && (
                <button
                  type="button"
                  title="Remove"
                  onClick={() => onChange(heads.filter((_, i) => i !== index))}
                >
                  ×
                </button>
              )}
            </span>
          ),
        )}
        {heads.length === 0 && <span className="muted">No headings set.</span>}
      </div>
      {canEdit && (
        <p className="sp-row">
          <input
            placeholder="Add a heading e.g. Swimming"
            value={adding}
            onChange={(e) => setAdding(e.target.value)}
            onKeyDown={(e) => {
              if (e.key !== 'Enter') return
              const text = adding.trim()
              if (text && !heads.some((h) => h.toLowerCase() === text.toLowerCase())) {
                onChange([...heads, text])
              }
              setAdding('')
            }}
          />
          <button
            onClick={() => {
              const text = adding.trim()
              if (text && !heads.some((h) => h.toLowerCase() === text.toLowerCase())) {
                onChange([...heads, text])
              }
              setAdding('')
            }}
          >
            Add heading
          </button>
        </p>
      )}
    </div>
  )
}

function Documents({ categories, canEdit }) {
  const [docs, setDocs] = useState([])
  const [form, setForm] = useState({ title: '', category: 'REGISTRATION', document_date: '', note: '' })
  const [file, setFile] = useState(null)
  const [message, setMessage] = useState('')
  const fileRef = useRef(null)

  const load = useCallback(() => {
    apiGet('/api/school-documents/?page_size=200')
      .then((d) => setDocs(d.results || d))
      .catch(() => setDocs([]))
  }, [])
  useEffect(load, [load])

  async function upload() {
    if (!form.title.trim() || !file) {
      setMessage('Give the document a name and choose a file.')
      return
    }
    const body = new FormData()
    body.append('title', form.title.trim())
    body.append('category', form.category)
    body.append('note', form.note)
    if (form.document_date) body.append('document_date', form.document_date)
    body.append('file', file)
    const res = await apiUpload('/api/school-documents/', body)
    if (res.ok) {
      setForm({ title: '', category: form.category, document_date: '', note: '' })
      setFile(null)
      if (fileRef.current) fileRef.current.value = ''
      setMessage('Filed.')
      load()
    } else {
      setMessage(res.data?.detail || JSON.stringify(res.data))
    }
  }

  async function remove(doc) {
    if (!window.confirm(`Remove "${doc.title}" from the school's files?`)) return
    await apiWrite(`/api/school-documents/${doc.id}/`, {}, { method: 'DELETE' })
    load()
  }

  const byCategory = categories
    .map((c) => ({ ...c, items: docs.filter((d) => d.category === c.value) }))
    .filter((c) => c.items.length)

  return (
    <div className="card">
      <h3>School documents</h3>
      <p className="muted">
        Registration certificates, policies, MoE circulars, board minutes — filed
        where the office can find them from any device.
      </p>

      {canEdit && (
        <div className="sp-upload">
          <input
            placeholder="What is it? e.g. Registration certificate 2026"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
          />
          <select
            value={form.category}
            onChange={(e) => setForm({ ...form, category: e.target.value })}
          >
            {categories.map((c) => (
              <option key={c.value} value={c.value}>{c.label}</option>
            ))}
          </select>
          <input
            type="date"
            title="The date on the document itself"
            value={form.document_date}
            onChange={(e) => setForm({ ...form, document_date: e.target.value })}
          />
          <input ref={fileRef} type="file" onChange={(e) => setFile(e.target.files[0])} />
          <button className="primary" onClick={upload}>File it</button>
        </div>
      )}
      {message && <p className="muted">{message}</p>}

      {docs.length === 0 && <p className="muted">Nothing filed yet.</p>}
      {byCategory.map((group) => (
        <div key={group.value} className="sp-doc-group">
          <h4>{group.label}</h4>
          <table>
            <thead>
              <tr><th>Document</th><th>Dated</th><th>Filed by</th><th></th></tr>
            </thead>
            <tbody>
              {group.items.map((doc) => (
                <tr key={doc.id}>
                  <td>
                    <b>{doc.title}</b>
                    {doc.note && <><br /><span className="muted">{doc.note}</span></>}
                  </td>
                  <td>{doc.document_date || '—'}</td>
                  <td>{doc.uploaded_by_name || '—'}</td>
                  <td className="sp-doc-actions">
                    <a href={doc.file_url} target="_blank" rel="noreferrer">Open</a>
                    <a href={doc.file_url} download>Download</a>
                    {canEdit && <button onClick={() => remove(doc)}>Remove</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  )
}

export default function SchoolProfile() {
  const [profile, setProfile] = useState(null)
  const [draft, setDraft] = useState({})
  const [message, setMessage] = useState('')
  const [saving, setSaving] = useState(false)
  const logoRef = useRef(null)

  const load = useCallback(() => {
    apiGet('/api/my-school/profile/')
      .then((d) => {
        setProfile(d)
        setDraft({
          contact_phone: d.contact_phone, alt_phone: d.alt_phone,
          contact_email: d.contact_email, postal_address: d.postal_address,
          website: d.website, motto: d.motto,
        })
      })
      .catch(() => setProfile(null))
  }, [])
  useEffect(load, [load])

  if (!profile) return <p className="muted">Loading the school profile…</p>
  const canEdit = Boolean(profile.can_edit)

  async function saveDetails() {
    setSaving(true)
    const res = await apiWrite('/api/my-school/profile/', draft, { method: 'PATCH' })
    setSaving(false)
    setMessage(res.ok ? 'Saved.' : res.data?.detail || JSON.stringify(res.data))
    if (res.ok) load()
  }

  async function saveHeads(heads) {
    // Headings save on the spot: an unsaved chip list is a trap, because the
    // fee grid reads this the moment you open it.
    setProfile({ ...profile, fee_columns: heads, vote_heads: heads })
    const res = await apiWrite(
      '/api/my-school/profile/', { vote_heads: heads }, { method: 'PATCH' },
    )
    if (!res.ok) {
      setMessage('Could not save the headings.')
      load()
    }
  }

  async function uploadLogo(file) {
    if (!file) return
    const body = new FormData()
    body.append('logo', file)
    const res = await apiUpload('/api/my-school/profile/', body, { method: 'PATCH' })
    if (logoRef.current) logoRef.current.value = ''
    setMessage(res.ok ? 'Badge updated.' : 'Could not upload that image.')
    load()
  }

  async function removeLogo() {
    if (!window.confirm('Remove the school badge?')) return
    const body = new FormData()
    body.append('logo', '')
    await apiUpload('/api/my-school/profile/', body, { method: 'PATCH' })
    load()
  }

  return (
    <div>
      <div className="card">
        <h3>{profile.name}</h3>
        <Facts profile={profile} />
        {!canEdit && (
          <p className="muted">
            You can see the school's details here; only the school administrator
            can change them.
          </p>
        )}
      </div>

      <div className="card">
        <h3>School badge</h3>
        <p className="muted">
          Printed at the top of report cards, fee notes and admission forms.
        </p>
        <div className="sp-logo">
          {profile.logo_url ? (
            <img src={profile.logo_url} alt={`${profile.name} badge`} />
          ) : (
            <div className="sp-logo-empty">No badge</div>
          )}
          {canEdit && (
            <div className="sp-row">
              <input
                ref={logoRef}
                type="file"
                accept="image/*"
                onChange={(e) => uploadLogo(e.target.files[0])}
              />
              {profile.logo_url && <button onClick={removeLogo}>Remove</button>}
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <h3>Contacts</h3>
        <p className="muted">
          The school's own lines, kept apart from whoever currently holds the
          admin account — that person changes; the office number should not
          have to.
        </p>
        <div className="sp-grid">
          <Field label="Office phone" value={draft.contact_phone} disabled={!canEdit}
            placeholder="07XX XXX XXX"
            onChange={(v) => setDraft({ ...draft, contact_phone: v })} />
          <Field label="Second phone" value={draft.alt_phone} disabled={!canEdit}
            placeholder="Optional"
            onChange={(v) => setDraft({ ...draft, alt_phone: v })} />
          <Field label="Email" type="email" value={draft.contact_email} disabled={!canEdit}
            placeholder="office@school.ac.ke"
            onChange={(v) => setDraft({ ...draft, contact_email: v })} />
          <Field label="Postal address" value={draft.postal_address} disabled={!canEdit}
            placeholder="P.O. Box 42, Nyeri"
            onChange={(v) => setDraft({ ...draft, postal_address: v })} />
          <Field label="Website" value={draft.website} disabled={!canEdit}
            placeholder="school.ac.ke"
            onChange={(v) => setDraft({ ...draft, website: v })} />
          <Field label="Motto" value={draft.motto} disabled={!canEdit}
            placeholder="Education is light"
            onChange={(v) => setDraft({ ...draft, motto: v })} />
        </div>
        {canEdit && (
          <p className="sp-row">
            <button className="primary" onClick={saveDetails} disabled={saving}>
              {saving ? 'Saving…' : 'Save details'}
            </button>
            {message && <span className="muted">{message}</span>}
          </p>
        )}
      </div>

      <VoteHeads
        heads={profile.fee_columns || []}
        canEdit={canEdit}
        onChange={saveHeads}
      />

      <Documents categories={profile.document_categories || []} canEdit={canEdit} />
    </div>
  )
}
