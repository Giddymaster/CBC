import { useRef, useState } from 'react'
import { apiUpload, getToken } from './api.js'

/** The shared shape of every spreadsheet import: choose a CSV, check it (dry
 * run with row-numbered problems), then commit what validated. The learner,
 * staff and facilities importers all speak this protocol. */
export default function ImportCard({
  title, blurb, endpoint, templateName, columns, commitNoun, onDone, extraResult,
}) {
  const [file, setFile] = useState(null)
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const inputRef = useRef(null)

  async function send(commit) {
    if (!file) {
      setMessage('Choose a CSV file first.')
      return
    }
    setBusy(true)
    setMessage('')
    const body = new FormData()
    body.append('file', file)
    if (commit) body.append('commit', 'true')
    const res = await apiUpload(endpoint, body)
    setBusy(false)
    if (!res.ok && !res.data) {
      setMessage('The upload failed.')
      return
    }
    setResult(res.data)
    if (res.data?.committed) {
      setMessage(`${res.data.created} ${commitNoun} added.`)
      setFile(null)
      if (inputRef.current) inputRef.current.value = ''
      onDone?.()
    } else if (res.data?.detail) {
      setMessage(res.data.detail)
    }
  }

  async function downloadTemplate() {
    const res = await fetch(endpoint, {
      headers: { Authorization: `Token ${getToken()}` },
    })
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = templateName
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="card">
      <h3>{title}</h3>
      <p className="muted">{blurb}</p>

      <p style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap', alignItems: 'center' }}>
        <input
          ref={inputRef}
          type="file"
          accept=".csv,text/csv"
          onChange={(e) => { setFile(e.target.files?.[0] || null); setResult(null) }}
        />
        <button onClick={() => send(false)} disabled={busy || !file}>
          {busy ? 'Checking…' : 'Check the file'}
        </button>
        <button onClick={downloadTemplate}>Download template</button>
      </p>
      {message && <p className="muted">{message}</p>}

      {result && result.committed && extraResult?.(result)}

      {result && !result.committed && (
        <>
          <p>
            <b>{result.ready}</b> row{result.ready === 1 ? '' : 's'} ready
            {result.problems.length > 0 && (
              <> · <span className="error">{result.problems.length} with problems</span></>
            )}
          </p>

          {result.problems.length > 0 && (
            <div className="sync-failures">
              <b>These rows will be skipped:</b>
              <ul>
                {result.problems.slice(0, 20).map((p, i) => (
                  <li key={i}>
                    Row {p.row}{p.name ? ` (${p.name})` : ''} — {p.errors.join('; ')}
                  </li>
                ))}
              </ul>
              {result.problems.length > 20 && (
                <p className="muted">…and {result.problems.length - 20} more.</p>
              )}
            </div>
          )}

          {result.preview.length > 0 && (
            <>
              <table>
                <thead>
                  <tr>
                    <th>Row</th>
                    {columns.map((c) => <th key={c.key}>{c.label}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {result.preview.map((p) => (
                    <tr key={p.row}>
                      <td className="muted">{p.row}</td>
                      {columns.map((c) => (
                        <td key={c.key}>
                          {c.render ? c.render(p[c.key]) : (p[c.key] || '—')}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              <p>
                <button className="primary" onClick={() => send(true)} disabled={busy}>
                  Add {result.ready} {commitNoun}
                </button>
              </p>
            </>
          )}
        </>
      )}
    </div>
  )
}
