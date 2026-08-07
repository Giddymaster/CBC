import { useEffect, useState } from 'react'
import { ParentThreads } from './ParentMessages.jsx'
import { apiGet } from './api.js'
import { gradeLabel } from './format.js'
import { ActionCard, ActionGrid, BottomNav, PortalHero } from './portalUi.jsx'

const PARENT_NAV = [
  { key: 'Dashboard', label: 'Dashboard', icon: 'grid' },
  { key: 'Results', label: 'Results', icon: 'clipboard' },
  { key: 'Fees', label: 'Fees', icon: 'wallet' },
  { key: 'Messages', label: 'Messages', icon: 'chat' },
  { key: 'Announcements', label: 'News', icon: 'bell' },
]

function unpaidCount(child) {
  return child.fees.invoices.filter((inv) => inv.status !== 'PAID').length
}

/** One chip per child; the portal always acts on the chosen one. Hidden when
 * there is only one child — nothing to choose. */
function ChildPicker({ children, selected, onSelect }) {
  if (children.length < 2) return null
  return (
    <div className="hero-chips" style={{ marginBottom: '0.7rem' }}>
      {children.map((c) => (
        <button key={c.id} type="button"
          className={`grade-chip${c.id === selected ? ' on' : ''}`}
          onClick={() => onSelect(c.id)}>
          {c.name.split(' ')[0]}
        </button>
      ))}
    </div>
  )
}

function ResultsTable({ child }) {
  const areas = child.report_card.learning_areas
  if (Object.keys(areas).length === 0) {
    return <p className="muted">No assessment records yet this year.</p>
  }
  return (
    <table>
      <thead>
        <tr><th>Learning area</th><th>Assessment</th><th>Marks</th><th>Level</th></tr>
      </thead>
      <tbody>
        {Object.entries(areas).flatMap(([area, kinds]) =>
          Object.entries(kinds).map(([kind, s]) => (
            <tr key={area + kind}>
              <td>{area}</td>
              <td>{kind}</td>
              <td>{s.marks} / {s.max_marks}</td>
              <td><span className={`level ${s.competency_level}`}>{s.competency_level}</span></td>
            </tr>
          )),
        )}
      </tbody>
    </table>
  )
}

function FeesCard({ child }) {
  const { fees } = child
  return (
    <div className="card">
      <h3>{child.name}</h3>
      <p>
        Outstanding balance: <b>KES {fees.total_balance}</b>
      </p>
      {fees.invoices.length === 0 ? (
        <p className="muted">No invoices yet.</p>
      ) : (
        <table>
          <thead>
            <tr><th>Invoice</th><th>Due</th><th>Paid</th><th>Balance</th><th>Status</th></tr>
          </thead>
          <tbody>
            {fees.invoices.map((inv) => (
              <tr key={inv.id}>
                <td>#{inv.id}</td>
                <td>KES {inv.due}</td>
                <td>KES {inv.paid}</td>
                <td><b>KES {inv.balance}</b></td>
                <td>
                  <span className={`badge ${inv.status === 'PAID' ? 'online' : 'queued'}`}>
                    {inv.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function Announcements({ items }) {
  return (
    <div className="card">
      <h3>Announcements</h3>
      {items.length === 0 && <p className="muted">Nothing yet.</p>}
      {items.map((a) => (
        <p key={a.id}>
          <b>{a.title}</b> <span className="muted">({a.date})</span>
          <br />
          {a.body}{' '}
          {a.meeting_link && (
            <a href={a.meeting_link} target="_blank" rel="noreferrer">Join meeting</a>
          )}
        </p>
      ))}
    </div>
  )
}

export default function ParentPortal() {
  const [summary, setSummary] = useState(null)
  const [error, setError] = useState('')
  const [tab, setTab] = useState('Dashboard')
  const [childId, setChildId] = useState(null)

  useEffect(() => {
    apiGet('/api/parent/summary/').then(setSummary).catch((e) => setError(e.message))
  }, [])

  if (error) return <div className="error">{error}</div>
  if (!summary) return <p className="muted">Loading…</p>

  const children = summary.children
  const child = children.find((c) => c.id === childId) || children[0]
  const openTab = (name) => { setTab(name); window.scrollTo(0, 0) }

  if (children.length === 0) {
    return (
      <div className="card">
        <h3>{summary.guardian.name}</h3>
        <p className="muted">
          No active learners are linked to this account yet — ask the school office
          to link your child.
        </p>
      </div>
    )
  }

  const unpaid = unpaidCount(child)
  const balance = Number(child.fees.total_balance)

  return (
    <div className="portal-shell">
      <nav className="tabs">
        {PARENT_NAV.map(({ key }) => (
          <button key={key} className={tab === key ? 'active' : ''}
            onClick={() => openTab(key)}>
            {key}
          </button>
        ))}
      </nav>

      {tab === 'Dashboard' && (
        <>
          <ChildPicker children={children} selected={child.id} onSelect={setChildId} />
          <PortalHero
            icon="user"
            title={child.name}
            subtitle={`${summary.guardian.name} · ${summary.school} · ${summary.year}`}
            chips={[
              `${gradeLabel(child.grade)}${child.stream ? ` ${child.stream}` : ''}`,
              ...(balance > 0 ? [`KES ${child.fees.total_balance} due`] : ['Fees cleared']),
            ]}
          />
          <ActionGrid>
            <ActionCard icon="clipboard" tone="green" title="Exam Report"
              desc="Detailed results and performance, area by area."
              cta="View results" onOpen={() => openTab('Results')} />
            <ActionCard icon="wallet" tone="orange" title="Fee Balance"
              desc="Payments made and what is still outstanding."
              cta="Check fees" badge={unpaid} onOpen={() => openTab('Fees')} />
            <ActionCard icon="chat" tone="blue" title="Messages"
              desc="Talk to your child's teachers."
              cta="Open messages" onOpen={() => openTab('Messages')} />
            <ActionCard icon="bell" tone="purple" title="Announcements"
              desc="Notices and events from the school."
              cta="Read notices" onOpen={() => openTab('Announcements')} />
          </ActionGrid>
        </>
      )}

      {tab === 'Results' && (
        <>
          <ChildPicker children={children} selected={child.id} onSelect={setChildId} />
          <div className="card">
            <h3>
              {child.name} — {gradeLabel(child.grade)} {child.stream}
            </h3>
            <ResultsTable child={child} />
          </div>
        </>
      )}

      {tab === 'Fees' && (
        <>
          <ChildPicker children={children} selected={child.id} onSelect={setChildId} />
          <FeesCard child={child} />
        </>
      )}

      {tab === 'Messages' && <ParentThreads />}
      {tab === 'Announcements' && <Announcements items={summary.announcements} />}

      <BottomNav items={PARENT_NAV} active={tab} onSelect={openTab} />
    </div>
  )
}
