import { useCallback, useEffect, useState } from 'react'
import { apiGet, apiWrite } from './api.js'

function Bubble({ message, mine }) {
  return (
    <div className={`bubble-row ${mine ? 'mine' : ''}`}>
      <div className="bubble">
        <div className="bubble-who">
          {message.sender_name}
          <span className="muted">
            {' '}{new Date(message.created_at).toLocaleString()}
          </span>
        </div>
        {message.body}
      </div>
    </div>
  )
}

/** Parent side: one conversation per child per contact. */
export function ParentThreads() {
  const [data, setData] = useState(null)
  const [drafts, setDrafts] = useState({})
  const [message, setMessage] = useState('')

  const load = useCallback(() => {
    apiGet('/api/parent/threads/').then(setData).catch(() => setData(null))
  }, [])
  useEffect(load, [load])

  if (!data) return <p className="muted">Loading…</p>

  const key = (t) => `${t.learner}-${t.staff}`

  async function send(thread) {
    const body = (drafts[key(thread)] || '').trim()
    if (!body) return
    const res = await apiWrite('/api/communication/parent-messages/', {
      learner: thread.learner,
      guardian: data.guardian_id,
      staff: thread.staff,
      body,
    })
    if (res.ok) {
      setDrafts((d) => ({ ...d, [key(thread)]: '' }))
      load()
    } else {
      setMessage(res.data?.detail || 'Could not send that message.')
    }
  }

  return (
    <div>
      {message && <p className="error">{message}</p>}
      {data.threads.length === 0 && (
        <div className="card">
          <p className="muted">
            No one is listed for your children yet. The school assigns a class
            teacher — once it has, you can write to them here.
          </p>
        </div>
      )}
      {data.threads.map((thread) => (
        <div className="card" key={key(thread)}>
          <h3>
            {thread.staff_name}{' '}
            <span className="muted">{thread.staff_role}</span>
          </h3>
          <p className="muted">About {thread.learner_name}</p>

          <div className="thread">
            {thread.messages.length === 0 && (
              <p className="muted">No messages yet — start the conversation below.</p>
            )}
            {thread.messages.map((m) => (
              <Bubble key={m.id} message={m} mine={m.from_parent} />
            ))}
          </div>

          <p style={{ display: 'flex', gap: '0.5rem' }}>
            <input
              placeholder={`Message ${thread.staff_name.split(' ')[0]}…`}
              value={drafts[key(thread)] || ''}
              onChange={(e) => setDrafts({ ...drafts, [key(thread)]: e.target.value })}
              onKeyDown={(e) => { if (e.key === 'Enter') send(thread) }}
              style={{ flex: 1, padding: '0.45rem' }}
            />
            <button className="primary" onClick={() => send(thread)}>Send</button>
          </p>
        </div>
      ))}
    </div>
  )
}

/** Staff side: parents who have written, grouped by child. */
export function StaffParentThreads() {
  const [threads, setThreads] = useState([])
  const [drafts, setDrafts] = useState({})
  const [message, setMessage] = useState('')

  const load = useCallback(() => {
    apiGet('/api/staff/parent-threads/')
      .then((d) => setThreads(d.threads || []))
      .catch(() => setThreads([]))
  }, [])
  useEffect(load, [load])

  const key = (t) => `${t.learner}-${t.guardian}`

  async function reply(thread) {
    const body = (drafts[key(thread)] || '').trim()
    if (!body) return
    const res = await apiWrite('/api/communication/parent-messages/', {
      learner: thread.learner,
      guardian: thread.guardian,
      staff: thread.messages[0].staff,
      body,
    })
    if (res.ok) {
      setDrafts((d) => ({ ...d, [key(thread)]: '' }))
      load()
    } else {
      setMessage(res.data?.detail || 'Could not send that reply.')
    }
  }

  return (
    <div>
      <div className="card">
        <h3>Parents</h3>
        <p className="muted">
          Messages from the parents of learners in your class. Replies go straight
          back to them.
        </p>
        {message && <p className="error">{message}</p>}
        {threads.length === 0 && <p className="muted">No parent has written to you yet.</p>}
      </div>

      {threads.map((thread) => (
        <div className="card" key={key(thread)}>
          <h3>
            {thread.guardian_name}
            {thread.unread > 0 && (
              <> <span className="badge queued">{thread.unread} new</span></>
            )}
          </h3>
          <p className="muted">
            About {thread.learner_name}
            {thread.guardian_phone && (
              <> · <a href={`tel:${thread.guardian_phone}`}>{thread.guardian_phone}</a></>
            )}
          </p>

          <div className="thread">
            {thread.messages.map((m) => (
              <Bubble key={m.id} message={m} mine={!m.from_parent} />
            ))}
          </div>

          <p style={{ display: 'flex', gap: '0.5rem' }}>
            <input
              placeholder="Reply…"
              value={drafts[key(thread)] || ''}
              onChange={(e) => setDrafts({ ...drafts, [key(thread)]: e.target.value })}
              onKeyDown={(e) => { if (e.key === 'Enter') reply(thread) }}
              style={{ flex: 1, padding: '0.45rem' }}
            />
            <button className="primary" onClick={() => reply(thread)}>Send</button>
          </p>
        </div>
      ))}
    </div>
  )
}
