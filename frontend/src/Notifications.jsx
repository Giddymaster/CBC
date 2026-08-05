import { useCallback, useEffect, useRef, useState } from 'react'
import { apiGet, apiWrite } from './api.js'

const KIND_LABEL = {
  MESSAGE: 'Message',
  TASK: 'Assigned work',
  REVIEW: 'Awaiting your approval',
  RETURNED: 'Returned for changes',
}
const KIND_BADGE = {
  MESSAGE: 'queued',
  TASK: 'queued',
  REVIEW: 'queued',
  RETURNED: 'offline',
}

function timeAgo(iso) {
  if (!iso) return ''
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return new Date(iso).toLocaleDateString()
}

/** The bell in the topbar: anything waiting on this staff member. */
export default function Notifications({ onOpenTeam }) {
  const [data, setData] = useState({ count: 0, items: [], unread_messages: 0 })
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  const load = useCallback(() => {
    apiGet('/api/notifications/')
      .then(setData)
      .catch(() => {}) // a portal-less account (parent) simply has no bell
  }, [])

  useEffect(() => {
    load()
    const timer = setInterval(load, 60_000)
    return () => clearInterval(timer)
  }, [load])

  // Click anywhere else closes the panel.
  useEffect(() => {
    if (!open) return
    const away = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', away)
    return () => document.removeEventListener('mousedown', away)
  }, [open])

  async function markRead() {
    await apiWrite('/api/notifications/', {})
    load()
  }

  return (
    <div className="notif" ref={ref}>
      <button
        className="notif-bell"
        onClick={() => setOpen((o) => !o)}
        title="Notifications"
        aria-label={`Notifications (${data.count})`}
      >
        <span aria-hidden="true">🔔</span>
        {data.count > 0 && <span className="notif-dot">{data.count}</span>}
      </button>

      {open && (
        <div className="notif-panel">
          <div className="notif-head">
            <b>Notifications</b>
            {data.unread_messages > 0 && (
              <button onClick={markRead}>Mark messages read</button>
            )}
          </div>

          {data.items.length === 0 && (
            <p className="notif-empty">Nothing waiting on you.</p>
          )}

          {data.items.map((item) => (
            <div
              key={item.id}
              className={`notif-item${item.from_id && onOpenTeam ? ' notif-clickable' : ''}`}
              onClick={() => {
                if (item.from_id && onOpenTeam) {
                  onOpenTeam(item.from_id)
                  setOpen(false)
                }
              }}
            >
              <div className="notif-item-head">
                <span className={`badge ${KIND_BADGE[item.kind]}`}>
                  {KIND_LABEL[item.kind]}
                </span>
                <span className="notif-time">{timeAgo(item.at)}</span>
              </div>
              <div className="notif-title">{item.title}</div>
              <div className="notif-body">{item.body}</div>
              {item.due_date && (
                <div className={item.overdue ? 'notif-overdue' : 'notif-time'}>
                  Due {item.due_date}{item.overdue ? ' — overdue' : ''}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
