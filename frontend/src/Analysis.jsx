import { useCallback, useEffect, useState } from 'react'
import { apiGet, apiWrite } from './api.js'
import { gradeLabel } from './format.js'

const LEVEL_COLOUR = { EE: '#2f855a', ME: '#3182ce', AE: '#dd6b20', BE: '#c53030' }
const LEVEL_NAME = {
  EE: 'Exceeding', ME: 'Meeting', AE: 'Approaching', BE: 'Below',
}

/** Competency spread as a single stacked bar — the shape reads faster than four numbers. */
function CompetencyBar({ competency }) {
  if (!competency?.total) return <span className="muted">—</span>
  return (
    <div>
      <div className="spread-bar" title={`${competency.total} scores`}>
        {['EE', 'ME', 'AE', 'BE'].map((level) => {
          const pct = competency.percent[level]
          if (!pct) return null
          return (
            <span
              key={level}
              style={{ width: `${pct}%`, background: LEVEL_COLOUR[level] }}
              title={`${LEVEL_NAME[level]} expectation: ${competency.counts[level]} (${pct}%)`}
            />
          )
        })}
      </div>
      <span className="muted">
        {competency.at_or_above_expectation}% at or above expectation
      </span>
    </div>
  )
}

function Movement({ value }) {
  if (value === null || value === undefined) {
    return <span className="muted">first term</span>
  }
  const up = value > 0
  const flat = value === 0
  return (
    <span style={{ color: flat ? '#718096' : up ? '#2f855a' : '#c53030', fontWeight: 600 }}>
      {flat ? '±0' : `${up ? '▲ +' : '▼ '}${value}`} pts
    </span>
  )
}

function TeacherDetail({ teacherId, onBack }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    apiGet(`/api/teachers/${teacherId}/analysis/`)
      .then(setData)
      .catch((e) => setError(e.message))
  }, [teacherId])

  if (error) return <div className="error">{error}</div>
  if (!data) return <p className="muted">Loading…</p>

  return (
    <div>
      {onBack && <p><button onClick={onBack}>← All teachers</button></p>}
      <div className="card">
        <h3>{data.teacher}</h3>
        <p className="muted">{data.note}</p>
        {data.classes.length === 0 ? (
          <p className="muted">Nothing to show yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Class</th><th>Learners</th><th>Mean</th>
                <th>Competency spread</th><th>Since last term</th><th>Terms</th>
              </tr>
            </thead>
            <tbody>
              {data.classes.map((row, i) => (
                <tr key={i}>
                  <td>
                    <b>{row.learning_area}</b>
                    <div className="muted">
                      {row.grade_label}{row.stream ? ` ${row.stream}` : ''}
                    </div>
                  </td>
                  <td>{row.learners}</td>
                  <td>
                    {row.withheld ? (
                      <span className="muted" title={row.withheld_reason}>withheld</span>
                    ) : (
                      <b>{row.mean}%</b>
                    )}
                  </td>
                  <td style={{ minWidth: '12rem' }}>
                    <CompetencyBar competency={row.competency} />
                  </td>
                  <td><Movement value={row.movement} /></td>
                  <td className="muted">
                    {row.timeline.map((t) => `${t.label} ${t.mean}%`).join(' → ')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

function PdRecords() {
  const [records, setRecords] = useState([])
  const [summary, setSummary] = useState([])
  const [form, setForm] = useState({
    title: '', provider: '', completed_on: '', tpd_points: 0,
  })
  const [message, setMessage] = useState('')

  const load = useCallback(() => {
    apiGet('/api/pd-records/?page_size=100')
      .then((d) => setRecords(d.results || d))
      .catch(() => setRecords([]))
    apiGet('/api/pd-records/summary/').then(setSummary).catch(() => setSummary([]))
  }, [])
  useEffect(load, [load])

  async function add(e) {
    e.preventDefault()
    if (!form.title.trim() || !form.completed_on) {
      setMessage('A title and a completion date are needed.')
      return
    }
    const res = await apiWrite('/api/pd-records/', {
      ...form,
      tpd_points: Number(form.tpd_points) || 0,
    })
    setMessage(res.ok ? 'Recorded.' : `Failed: ${JSON.stringify(res.data)}`)
    if (res.ok) {
      setForm({ title: '', provider: '', completed_on: '', tpd_points: 0 })
      load()
    }
  }

  return (
    <div className="card">
      <h3>Professional development</h3>
      <p className="muted">
        Training completed, with TPD points — the unit TSC counts. Log your own; the
        admin can log anyone's.
      </p>
      <form onSubmit={add} style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
        <input placeholder="Course or workshop" value={form.title}
          onChange={(e) => setForm({ ...form, title: e.target.value })}
          style={{ padding: '0.4rem', minWidth: '16rem' }} />
        <input placeholder="Provider e.g. TSC, KICD" value={form.provider}
          onChange={(e) => setForm({ ...form, provider: e.target.value })}
          style={{ padding: '0.4rem' }} />
        <label className="muted">
          Completed{' '}
          <input type="date" value={form.completed_on}
            onChange={(e) => setForm({ ...form, completed_on: e.target.value })} />
        </label>
        <label className="muted">
          TPD points{' '}
          <input type="number" min="0" value={form.tpd_points}
            onChange={(e) => setForm({ ...form, tpd_points: e.target.value })}
            style={{ width: '5rem', padding: '0.4rem' }} />
        </label>
        <button className="primary" type="submit">Add</button>
      </form>
      {message && <p className="muted">{message}</p>}

      {records.length > 0 && (
        <table>
          <thead>
            <tr><th>Course</th><th>Provider</th><th>Completed</th><th>TPD points</th><th>Teacher</th></tr>
          </thead>
          <tbody>
            {records.map((r) => (
              <tr key={r.id}>
                <td>{r.title}</td>
                <td className="muted">{r.provider || '—'}</td>
                <td className="muted">{r.completed_on}</td>
                <td>{r.tpd_points}</td>
                <td className="muted">{r.teacher_name}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {summary.length > 1 && (
        <>
          <h4>TPD points by teacher</h4>
          <table>
            <thead><tr><th>Teacher</th><th>Points</th></tr></thead>
            <tbody>
              {summary.map((s) => (
                <tr key={s.teacher}><td>{s.name}</td><td>{s.tpd_points}</td></tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  )
}

function PeerReview() {
  const [queue, setQueue] = useState(null)
  const [drafts, setDrafts] = useState({})
  const [message, setMessage] = useState('')

  const load = useCallback(() => {
    apiGet('/api/peer-review/queue/').then(setQueue).catch(() => setQueue(null))
  }, [])
  useEffect(load, [load])

  async function submit(scheme, verdict) {
    const comment = (drafts[scheme.id] || '').trim()
    if (!comment) {
      setMessage('Write a comment — a verdict on its own is not feedback.')
      return
    }
    const res = await apiWrite('/api/peer-reviews/', {
      scheme: scheme.id, verdict, comment,
    })
    setMessage(res.ok ? 'Sent to your colleague.' : `Failed: ${JSON.stringify(res.data)}`)
    if (res.ok) {
      setDrafts((d) => ({ ...d, [scheme.id]: '' }))
      load()
    }
  }

  if (!queue) return null

  return (
    <div className="card">
      <h3>Peer review</h3>
      <p className="muted">
        Colleagues' schemes of work in subjects you teach. This is advice between
        teachers — it does not approve or reject the scheme, which stays with the head.
      </p>
      {message && <p className="muted">{message}</p>}
      {queue.schemes.length === 0 ? (
        <p className="muted">Nothing waiting for your view.</p>
      ) : (
        queue.schemes.map((s) => (
          <div key={s.id} className="passage">
            <div className="passage-head">
              <b>{s.learning_area}</b>
              <span className="muted">
                {gradeLabel(s.grade)} · Term {s.term} {s.year} · {s.teacher}
              </span>
              {s.peer_reviews > 0 && (
                <span className="badge queued">{s.peer_reviews} review(s)</span>
              )}
            </div>
            <p style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              <input
                placeholder="What would help your colleague?"
                value={drafts[s.id] || ''}
                onChange={(e) => setDrafts({ ...drafts, [s.id]: e.target.value })}
                style={{ flex: 1, minWidth: '16rem', padding: '0.4rem' }}
              />
              <button className="primary" onClick={() => submit(s, 'ENDORSE')}>
                Looks good
              </button>
              <button onClick={() => submit(s, 'SUGGEST')}>Send suggestions</button>
            </p>
          </div>
        ))
      )}
    </div>
  )
}

/** Admin view: every teacher, then drill into one. */
export default function Analysis() {
  const [overview, setOverview] = useState(null)
  const [selected, setSelected] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    apiGet('/api/school/analysis/')
      .then(setOverview)
      .catch((e) => setError(e.message))
  }, [])

  if (error) return <div className="error">{error}</div>
  if (selected) {
    return <TeacherDetail teacherId={selected} onBack={() => setSelected(null)} />
  }
  if (!overview) return <p className="muted">Loading…</p>

  return (
    <div>
      <div className="card">
        <h3>Teaching outcomes</h3>
        <p className="muted">{overview.note}</p>
        {overview.teachers.length === 0 ? (
          <p className="muted">
            No marks are attributed to any teacher yet. Outcomes are matched to
            teachers through their timetable requirements.
          </p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Teacher</th><th>Rank</th><th>Classes</th><th>Mean</th>
                <th>At or above expectation</th><th>Since last term</th><th></th>
              </tr>
            </thead>
            <tbody>
              {overview.teachers.map((t) => (
                <tr key={t.teacher_id}>
                  <td>{t.name}</td>
                  <td className="muted">{t.rank}</td>
                  <td>{t.classes}</td>
                  <td>{t.overall_mean === null ? <span className="muted">—</span> : `${t.overall_mean}%`}</td>
                  <td>
                    {t.at_or_above_expectation === null
                      ? <span className="muted">—</span>
                      : `${t.at_or_above_expectation}%`}
                  </td>
                  <td><Movement value={t.movement} /></td>
                  <td><button onClick={() => setSelected(t.teacher_id)}>Open</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <PdRecords />
    </div>
  )
}

export { PdRecords, PeerReview, TeacherDetail }
