import { useCallback, useEffect, useState } from 'react'
import { apiGet, apiWrite } from './api.js'
import { ALL_GRADES, gradeLabel } from './format.js'

const ACTIONS = [
  { value: 'PROMOTE', label: 'Move up' },
  { value: 'REPEAT', label: 'Repeat the year' },
  { value: 'TRANSFER', label: 'Transferred out' },
  { value: 'GRADUATE', label: 'Completed Grade 12' },
]
const ACTION_BADGE = {
  PROMOTE: 'online', REPEAT: 'queued', TRANSFER: 'offline', GRADUATE: 'online',
}
const STATUS_BADGE = { DRAFT: 'queued', APPLIED: 'online', REVERSED: 'offline' }

function Rationale({ data }) {
  if (!data || !Object.keys(data).length) return null
  if (!data.averages) return <span className="muted">{data.note || data.basis}</span>
  return (
    <span className="muted">
      {Object.entries(data.averages)
        .sort((a, b) => b[1] - a[1])
        .map(([code, avg]) => `${code} ${avg}%`)
        .join(' · ')}
    </span>
  )
}

function OutcomeRow({ row, pathways, editable, onChange }) {
  const isSenior = row.to_grade === 10 && row.action === 'PROMOTE'
  return (
    <tr>
      <td>
        {row.learner_name}
        <div className="muted">{row.admission_number}</div>
      </td>
      <td>{gradeLabel(row.from_grade)}</td>
      <td>
        {row.action === 'PROMOTE' ? (
          <b>{gradeLabel(row.to_grade)}</b>
        ) : (
          <span className="muted">—</span>
        )}
      </td>
      <td>
        {editable ? (
          <select
            value={row.action}
            onChange={(e) => onChange(row, { action: e.target.value })}
          >
            {ACTIONS.map((a) => (
              <option key={a.value} value={a.value}>{a.label}</option>
            ))}
          </select>
        ) : (
          <span className={`badge ${ACTION_BADGE[row.action]}`}>{row.action_label}</span>
        )}
      </td>
      <td>
        {isSenior ? (
          <>
            {editable ? (
              <select
                value={row.pathway || ''}
                onChange={(e) =>
                  onChange(row, { pathway: e.target.value ? Number(e.target.value) : null })
                }
                className={row.pathway ? undefined : 'needs-attention'}
              >
                <option value="">— choose a pathway —</option>
                {pathways.map((p) => (
                  <option key={p.id} value={p.id}>{p.description || p.code}</option>
                ))}
              </select>
            ) : (
              row.pathway_label || <span className="muted">—</span>
            )}
            <div><Rationale data={row.pathway_rationale} /></div>
          </>
        ) : (
          <span className="muted">—</span>
        )}
      </td>
    </tr>
  )
}

export default function Promotions() {
  const [info, setInfo] = useState(null)
  const [runs, setRuns] = useState([])
  const [active, setActive] = useState(null)
  const [outcomes, setOutcomes] = useState([])
  const [pathways, setPathways] = useState([])
  const [form, setForm] = useState({ from_year: '', to_year: '', grade: '' })
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [confirming, setConfirming] = useState(false)

  const load = useCallback(() => {
    apiGet('/api/promotions/transitions/')
      .then((data) => {
        setInfo(data)
        const year = data.current_year || new Date().getFullYear()
        setForm((f) => ({
          ...f,
          from_year: f.from_year || String(year),
          to_year: f.to_year || String(year + 1),
        }))
      })
      .catch(() => setInfo(null))
    apiGet('/api/promotions/runs/?page_size=50')
      .then((d) => setRuns(d.results || d))
      .catch(() => setRuns([]))
    apiGet('/api/pathways/?page_size=50')
      .then((d) => setPathways(d.results || d))
      .catch(() => setPathways([]))
  }, [])
  useEffect(load, [load])

  const openRun = useCallback(async (runId) => {
    const [run, rows] = await Promise.all([
      apiGet(`/api/promotions/runs/${runId}/`),
      apiGet(`/api/promotions/runs/${runId}/outcomes/`),
    ])
    setActive(run)
    setOutcomes(rows)
    setConfirming(false)
  }, [])

  // Reopen a draft left from a previous visit.
  useEffect(() => {
    if (info?.draft_run && !active) openRun(info.draft_run)
  }, [info, active, openRun])

  async function preview(e) {
    e.preventDefault()
    setBusy(true)
    setMessage('')
    const body = {
      from_year: Number(form.from_year),
      to_year: Number(form.to_year),
    }
    if (form.grade !== '') body.grade = Number(form.grade)
    const res = await apiWrite('/api/promotions/runs/', body)
    setBusy(false)
    if (!res.ok) {
      setMessage(res.data?.detail || JSON.stringify(res.data))
      return
    }
    load()
    openRun(res.data.id)
  }

  async function changeOutcome(row, patch) {
    setOutcomes((rows) => rows.map((r) => (r.id === row.id ? { ...r, ...patch } : r)))
    const res = await apiWrite(`/api/promotions/outcomes/${row.id}/`, patch, {
      method: 'PATCH',
    })
    if (!res.ok) {
      setMessage('That change did not save — reloading.')
      openRun(active.id)
    }
  }

  async function run(actionName) {
    setBusy(true)
    const res = await apiWrite(`/api/promotions/runs/${active.id}/${actionName}/`, {})
    setBusy(false)
    setConfirming(false)
    if (!res.ok) {
      setMessage(res.data?.detail || 'That did not work.')
      return
    }
    setMessage(
      actionName === 'apply'
        ? 'Promotion applied. Every register now shows the new year.'
        : 'Promotion reversed. Every learner is back where they were.',
    )
    load()
    openRun(active.id)
  }

  async function discard() {
    await apiWrite(`/api/promotions/runs/${active.id}/`, {}, { method: 'DELETE' })
    setActive(null)
    setOutcomes([])
    setMessage('Draft discarded.')
    load()
  }

  if (!info) return <p className="muted">Loading…</p>

  const editable = active?.status === 'DRAFT'
  const awaiting = outcomes.filter(
    (o) => o.action === 'PROMOTE' && o.to_grade === 10 && !o.pathway,
  ).length
  const counts = outcomes.reduce((acc, o) => {
    acc[o.action] = (acc[o.action] || 0) + 1
    return acc
  }, {})

  return (
    <div>
      <div className="card">
        <h3>End of year</h3>
        <p className="muted">
          Moves every learner up a grade, places Grade 9 on a Senior School pathway, and
          retires Grade 12. Nothing changes until you apply it, and an applied run can be
          reversed.
          {info.current_year && <> Current academic year: <b>{info.current_year}</b>.</>}
        </p>

        {!active && (
          <form
            onSubmit={preview}
            style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap', alignItems: 'center' }}
          >
            <label className="muted">
              Closing year{' '}
              <input
                type="number"
                value={form.from_year}
                onChange={(e) => setForm({ ...form, from_year: e.target.value })}
                style={{ width: '6rem', padding: '0.4rem' }}
              />
            </label>
            <label className="muted">
              New year{' '}
              <input
                type="number"
                value={form.to_year}
                onChange={(e) => setForm({ ...form, to_year: e.target.value })}
                style={{ width: '6rem', padding: '0.4rem' }}
              />
            </label>
            <label className="muted">
              Limit to{' '}
              <select
                value={form.grade}
                onChange={(e) => setForm({ ...form, grade: e.target.value })}
              >
                <option value="">Whole school</option>
                {ALL_GRADES.map((g) => (
                  <option key={g} value={g}>{gradeLabel(g)}</option>
                ))}
              </select>
            </label>
            <button className="primary" type="submit" disabled={busy}>
              {busy ? 'Preparing…' : 'Preview promotion'}
            </button>
          </form>
        )}
        {message && <p className="muted">{message}</p>}
      </div>

      {active && (
        <div className="card">
          <div className="page-header" style={{ marginBottom: '0.4rem' }}>
            <h3 style={{ margin: 0 }}>
              {active.from_year} → {active.to_year}{' '}
              <span className={`badge ${STATUS_BADGE[active.status]}`}>
                {active.status_label}
              </span>
            </h3>
            <button onClick={() => { setActive(null); setOutcomes([]) }}>Close</button>
          </div>

          <p className="muted">
            {outcomes.length} learners ·{' '}
            {ACTIONS.filter((a) => counts[a.value]).map((a) => (
              <span key={a.value}>{counts[a.value]} {a.label.toLowerCase()} · </span>
            ))}
          </p>

          {editable && awaiting > 0 && (
            <p className="sync-note">
              <b>{awaiting}</b> learner{awaiting > 1 ? 's' : ''} moving into Grade 10
              still need a pathway. The suggestion beside each one comes from their own
              marks — confirm or change it. MoE placement also weighs the learner's choice
              and the receiving school's capacity, so the decision is yours.
            </p>
          )}

          {editable && (
            <p style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              {confirming ? (
                <>
                  <b>
                    This moves {outcomes.length} learners. Reversible, but every register
                    changes now.
                  </b>
                  <button className="primary" onClick={() => run('apply')} disabled={busy}>
                    Yes, apply it
                  </button>
                  <button onClick={() => setConfirming(false)}>Cancel</button>
                </>
              ) : (
                <>
                  <button
                    className="primary"
                    onClick={() => setConfirming(true)}
                    disabled={busy || awaiting > 0}
                  >
                    Apply promotion
                  </button>
                  <button onClick={discard}>Discard draft</button>
                </>
              )}
            </p>
          )}

          {active.status === 'APPLIED' && (
            <p>
              <button onClick={() => run('revert')} disabled={busy}>
                Reverse this promotion
              </button>
            </p>
          )}

          <table>
            <thead>
              <tr>
                <th>Learner</th><th>From</th><th>To</th><th>Outcome</th>
                <th>Senior School pathway</th>
              </tr>
            </thead>
            <tbody>
              {outcomes.map((row) => (
                <OutcomeRow
                  key={row.id}
                  row={row}
                  pathways={pathways}
                  editable={editable}
                  onChange={changeOutcome}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {runs.length > 0 && (
        <div className="card">
          <h3>History</h3>
          <table>
            <thead>
              <tr><th>Years</th><th>Scope</th><th>Status</th><th>Learners</th><th>When</th><th></th></tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id}>
                  <td>{r.from_year} → {r.to_year}</td>
                  <td className="muted">
                    {r.grade === null ? 'Whole school' : gradeLabel(r.grade)}
                  </td>
                  <td>
                    <span className={`badge ${STATUS_BADGE[r.status]}`}>{r.status_label}</span>
                  </td>
                  <td>{r.summary?.total ?? '—'}</td>
                  <td className="muted">
                    {(r.applied_at || r.created_at || '').slice(0, 10)}
                  </td>
                  <td><button onClick={() => openRun(r.id)}>Open</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
