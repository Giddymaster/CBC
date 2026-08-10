import { useCallback, useEffect, useState } from 'react'
import { apiGet, apiWrite } from './api.js'
import { ALL_GRADES, gradeLabel } from './format.js'

/**
 * Bulk messages to parents — SMS or WhatsApp, one class or the whole school.
 *
 * The shape of this page is deliberate: you cannot reach the send button
 * without first seeing who this reaches and reading your own words back as one
 * real parent will get them. Every message is charged and none can be recalled,
 * so the preview is the point and the send is an afterthought.
 */

const AUDIENCES = [
  { value: 'SCHOOL', label: 'Every parent', hint: 'The whole school' },
  { value: 'GRADE', label: 'One class', hint: 'A grade, or a single stream' },
  { value: 'UNPAID', label: 'Fee balance', hint: 'Only families still owing' },
  { value: 'LEARNER', label: 'One learner', hint: "That child's parents" },
]

function segments(text) {
  if (!text) return 0
  return text.length <= 160 ? 1 : Math.ceil(text.length / 153)
}

export default function Messaging({ grade: navGrade }) {
  const [status, setStatus] = useState(null)
  const [form, setForm] = useState({
    title: '',
    body: '',
    channel: 'SMS',
    audience: navGrade ? 'GRADE' : 'SCHOOL',
    grade: navGrade ?? '',
    stream: '',
    learner: '',
  })
  const [streams, setStreams] = useState([])
  const [learnerQuery, setLearnerQuery] = useState('')
  const [learnerHits, setLearnerHits] = useState([])
  const [chosenLearner, setChosenLearner] = useState(null)
  const [preview, setPreview] = useState(null)
  const [history, setHistory] = useState([])
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  const loadHistory = useCallback(() => {
    apiGet('/api/communication/blasts/?page_size=25')
      .then((d) => setHistory(d.results || d))
      .catch(() => setHistory([]))
  }, [])

  useEffect(() => {
    apiGet('/api/communication/status/').then(setStatus).catch(() => setStatus(null))
    loadHistory()
  }, [loadHistory])

  // The nav's grade chip scopes the compose box, like every other page.
  useEffect(() => {
    if (navGrade === undefined || navGrade === null) return
    setForm((f) => ({ ...f, audience: 'GRADE', grade: navGrade, stream: '' }))
  }, [navGrade])

  useEffect(() => {
    if (form.audience !== 'GRADE' || form.grade === '') {
      setStreams([])
      return
    }
    apiGet(`/api/school/streams/?grade=${form.grade}`)
      .then((d) => setStreams(d.streams || []))
      .catch(() => setStreams([]))
  }, [form.audience, form.grade])

  // Any edit invalidates the preview — you never send words you did not check.
  const set = (patch) => {
    setForm((f) => ({ ...f, ...patch }))
    setPreview(null)
    setMessage('')
  }

  function insertField(field) {
    set({ body: `${form.body}${form.body.endsWith(' ') || !form.body ? '' : ' '}${field}` })
  }

  async function findLearner() {
    const q = learnerQuery.trim()
    if (!q) return
    const data = await apiGet(`/api/learners/?search=${encodeURIComponent(q)}&page_size=10`)
    setLearnerHits(data.results || data)
  }

  function chooseLearner(learner) {
    setChosenLearner(learner)
    setLearnerHits([])
    setLearnerQuery('')
    set({ learner: learner.id })
  }

  function payload() {
    const body = {
      title: form.title,
      body: form.body,
      channel: form.channel,
      audience: form.audience,
    }
    if (form.audience === 'GRADE') {
      body.grade = Number(form.grade)
      if (form.stream) body.stream = form.stream
    }
    if (form.audience === 'LEARNER') body.learner = form.learner
    return body
  }

  async function check() {
    setBusy(true)
    setMessage('')
    const res = await apiWrite('/api/communication/blasts/preview/', payload())
    setBusy(false)
    if (res.ok) {
      setPreview(res.data)
    } else {
      setMessage(res.data?.detail || Object.values(res.data || {}).flat().join(' '))
    }
  }

  async function send() {
    const channel = form.channel === 'SMS' ? 'SMS' : 'WhatsApp'
    const ok = window.confirm(
      `Send this ${channel} to ${preview.recipients} parent${preview.recipients === 1 ? '' : 's'}?` +
        (preview.live ? ' This cannot be undone.' : ' (No gateway configured — it will only be logged.)'),
    )
    if (!ok) return
    setBusy(true)
    const res = await apiWrite('/api/communication/blasts/', payload())
    setBusy(false)
    if (res.ok) {
      setMessage(`Sent to ${res.data.recipients} parents.`)
      setPreview(null)
      setForm((f) => ({ ...f, title: '', body: '' }))
      loadHistory()
    } else {
      setMessage(res.data?.detail || JSON.stringify(res.data))
    }
  }

  if (!status) return <p className="muted">Loading the message desk…</p>
  if (!status.may_send) {
    return (
      <div className="card">
        <h3>Messages to parents</h3>
        <p className="muted">
          Only the office, the bursar, the head teacher or the deputy may message
          parents on behalf of the school.
        </p>
      </div>
    )
  }

  const channel = form.channel === 'SMS' ? status.sms : status.whatsapp
  const count = form.body.length

  return (
    <div>
      <div className="card">
        <h3>Message parents</h3>

        <div className="msg-channels">
          {['SMS', 'WHATSAPP'].map((c) => (
            <button
              key={c}
              className={`msg-channel${form.channel === c ? ' active' : ''}`}
              onClick={() => set({ channel: c })}
            >
              <span aria-hidden="true">{c === 'SMS' ? '✉️' : '💬'}</span>
              {c === 'SMS' ? 'SMS' : 'WhatsApp'}
              <small>
                {(c === 'SMS' ? status.sms.live : status.whatsapp.live)
                  ? 'Live'
                  : 'Test mode'}
              </small>
            </button>
          ))}
        </div>

        {!channel.live && (
          <p className="msg-warn">
            No {form.channel === 'SMS' ? 'SMS' : 'WhatsApp'} gateway is configured
            yet, so messages are recorded here but not delivered to phones.
            {form.channel === 'WHATSAPP' &&
              ' WhatsApp also needs the school’s own Meta Business number, and Meta only allows school-initiated notices through a message template it has approved.'}
          </p>
        )}
        {form.channel === 'WHATSAPP' && channel.live && !status.whatsapp.template && (
          <p className="msg-warn">
            No approved WhatsApp template is set. Meta will only deliver free-form
            text to parents who messaged the school in the last 24 hours; everyone
            else will come back as failed.
          </p>
        )}

        <h4>Who is this for?</h4>
        <div className="msg-audience">
          {AUDIENCES.map((a) => (
            <button
              key={a.value}
              className={`msg-aud${form.audience === a.value ? ' active' : ''}`}
              onClick={() => set({ audience: a.value })}
            >
              <b>{a.label}</b>
              <small>{a.hint}</small>
            </button>
          ))}
        </div>

        {form.audience === 'GRADE' && (
          <p className="msg-row">
            <select value={form.grade} onChange={(e) => set({ grade: e.target.value, stream: '' })}>
              <option value="">Class…</option>
              {ALL_GRADES.map((g) => (
                <option key={g} value={g}>{gradeLabel(g)}</option>
              ))}
            </select>
            <select value={form.stream} onChange={(e) => set({ stream: e.target.value })}>
              <option value="">All streams</option>
              {streams.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </p>
        )}

        {form.audience === 'LEARNER' && (
          <div className="msg-row">
            {chosenLearner ? (
              <span className="stream-chip">
                {chosenLearner.admission_number} — {chosenLearner.first_name}{' '}
                {chosenLearner.last_name}
                <button type="button" title="Change" onClick={() => {
                  setChosenLearner(null)
                  set({ learner: '' })
                }}>×</button>
              </span>
            ) : (
              <>
                <input
                  placeholder="Admission number or name"
                  value={learnerQuery}
                  onChange={(e) => setLearnerQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && findLearner()}
                  style={{ padding: '0.4rem', minWidth: '14rem' }}
                />
                <button onClick={findLearner}>Find</button>
                {learnerHits.map((l) => (
                  <button key={l.id} className="msg-hit" onClick={() => chooseLearner(l)}>
                    {l.admission_number} — {l.first_name} {l.last_name}
                  </button>
                ))}
              </>
            )}
          </div>
        )}

        <h4>The message</h4>
        <input
          placeholder="Subject (kept for your records, not sent)"
          value={form.title}
          onChange={(e) => set({ title: e.target.value })}
          className="msg-title"
        />
        <textarea
          rows={5}
          className="msg-body"
          placeholder="Dear {name}, {learner} of {class} …"
          value={form.body}
          onChange={(e) => set({ body: e.target.value })}
        />
        <div className="msg-meta">
          <span>
            {count} characters
            {form.channel === 'SMS' && ` · ${segments(form.body)} SMS each`}
          </span>
        </div>

        <div className="msg-fields">
          <span className="muted">Insert:</span>
          {status.merge_fields.map((f) => (
            <button key={f.field} className="msg-chip" title={f.means}
              onClick={() => insertField(f.field)}>
              {f.field}
            </button>
          ))}
        </div>

        <p className="msg-row">
          <button className="primary" onClick={check} disabled={busy || !form.body.trim()}>
            {busy ? 'Working…' : 'Check who this reaches'}
          </button>
        </p>
        {message && <p className="muted">{message}</p>}
      </div>

      {preview && (
        <div className="card">
          <h3>Before you send</h3>
          {preview.recipients === 0 ? (
            <p className="muted">
              No parent in this group has a phone number on record — nothing would
              be sent. Check the guardians on the learners' profiles.
            </p>
          ) : (
            <>
              <p className="msg-count">
                <b>{preview.recipients}</b> parent{preview.recipients === 1 ? '' : 's'}
                {form.channel === 'SMS' && (
                  <> · <b>{preview.segments}</b> SMS to be charged</>
                )}
              </p>
              <p className="muted">
                Families with more than one child here are counted once. This is how
                the first few will read it:
              </p>
              <table>
                <thead>
                  <tr><th>Parent</th><th>Phone</th><th>Learner</th><th>Message</th></tr>
                </thead>
                <tbody>
                  {preview.sample.map((s) => (
                    <tr key={s.phone}>
                      <td>{s.name}</td>
                      <td>{s.phone}</td>
                      <td>{s.learner}<br /><span className="muted">{s.class}</span></td>
                      <td>{s.text}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="msg-row">
                <button className="primary" onClick={send} disabled={busy}>
                  {busy ? 'Sending…' : `Send to ${preview.recipients} parents`}
                </button>
                <button onClick={() => setPreview(null)}>Go back and edit</button>
              </p>
            </>
          )}
        </div>
      )}

      <div className="card">
        <h3>Sent messages</h3>
        {history.length === 0 && <p className="muted">Nothing has been sent yet.</p>}
        {history.map((b) => (
          <div key={b.id} className="msg-past">
            <div className="msg-past-head">
              <b>{b.title || b.body.slice(0, 48)}</b>
              <span className="badge queued">{b.channel === 'SMS' ? 'SMS' : 'WhatsApp'}</span>
              <span className="muted">
                {b.recipients} parent{b.recipients === 1 ? '' : 's'}
                {b.sent_by_name ? ` · ${b.sent_by_name}` : ''}
                {b.created_at ? ` · ${new Date(b.created_at).toLocaleString()}` : ''}
              </span>
            </div>
            <div className="msg-past-body">{b.body}</div>
            <div className="msg-past-delivery">
              {Object.entries(b.delivery || {}).map(([state, n]) => (
                <span key={state} className={`badge ${state === 'FAILED' ? 'offline' : 'queued'}`}>
                  {state === 'STUBBED' ? 'Logged only' : state.toLowerCase()}: {n}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
