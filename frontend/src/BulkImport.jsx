import { useRef, useState } from 'react'
import { apiUpload, getToken } from './api.js'
import { gradeLabel } from './format.js'

/** Upload a spreadsheet of learners: check first, then commit. */
export default function BulkImport({ onDone }) {
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
    const res = await apiUpload('/api/admissions/bulk/', body)
    setBusy(false)
    if (!res.ok && !res.data) {
      setMessage('The upload failed.')
      return
    }
    setResult(res.data)
    if (res.data?.committed) {
      setMessage(`${res.data.created} learners added to the register.`)
      setFile(null)
      if (inputRef.current) inputRef.current.value = ''
      onDone?.()
    } else if (res.data?.detail) {
      setMessage(res.data.detail)
    }
  }

  async function downloadTemplate() {
    const res = await fetch('/api/admissions/bulk/', {
      headers: { Authorization: `Token ${getToken()}` },
    })
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'learner_import_template.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="card">
      <h3>Import a class list</h3>
      <p className="muted">
        A whole intake from a spreadsheet. Save your file as CSV — the columns can be
        named however your school names them (<i>Adm No</i>, <i>DOB</i>, <i>Class</i> all
        work). Nothing is added until you have seen what it will create.
      </p>

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
                  <tr><th>Row</th><th>Name</th><th>Adm No</th><th>Grade</th><th>Stream</th><th>Guardian</th></tr>
                </thead>
                <tbody>
                  {result.preview.map((p) => (
                    <tr key={p.row}>
                      <td className="muted">{p.row}</td>
                      <td>{p.name}</td>
                      <td className="muted">{p.admission_number}</td>
                      <td>{gradeLabel(p.grade)}</td>
                      <td>{p.stream || '—'}</td>
                      <td className="muted">{p.guardian || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p>
                <button className="primary" onClick={() => send(true)} disabled={busy}>
                  Add {result.ready} learner{result.ready === 1 ? '' : 's'} to the register
                </button>
              </p>
            </>
          )}
        </>
      )}
    </div>
  )
}
