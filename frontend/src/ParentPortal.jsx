import { useEffect, useState } from 'react'
import { ParentThreads } from './ParentMessages.jsx'
import Learning from './Learning.jsx'
import Security from './Security.jsx'
import { apiGet } from './api.js'
import { gradeLabel } from './format.js'
import { ActionCard, ActionGrid, BackBar, BottomNav, PortalHero } from './portalUi.jsx'

const PARENT_NAV = [
  { key: 'Dashboard', label: 'Dashboard', icon: 'grid' },
  { key: 'Results', label: 'Results', icon: 'clipboard' },
  { key: 'Learn', label: 'Learn', icon: 'book' },
  { key: 'Fees', label: 'Fees', icon: 'wallet' },
  { key: 'Messages', label: 'Messages', icon: 'chat' },
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

const money = (n) => `KES ${Number(n || 0).toLocaleString(undefined, {
  minimumFractionDigits: 0, maximumFractionDigits: 0,
})}`

/** Who the child is on the school's register. */
function ProfileCard({ child }) {
  const p = child.profile || {}
  const facts = [
    ['Admission no', child.admission_number],
    ['UPI', p.upi],
    ['Class', `${gradeLabel(child.grade)}${child.stream ? ` ${child.stream}` : ''}`],
    ['Class teacher', p.class_teacher],
    ['Date of birth', p.date_of_birth],
    ['Gender', p.gender],
    ['Admitted', p.admission_date],
    ['Pathway', p.pathway],
  ]
  return (
    <div className="card">
      <div className="profile-head">
        {p.photo
          ? <img src={p.photo} alt="" className="learner-photo-lg" />
          : <span className="avatar avatar-lg">
              {child.name.split(' ').slice(0, 2).map((w) => w[0]).join('')}
            </span>}
        <div className="profile-headline">
          <h3>{child.name}</h3>
          <p className="profile-title">
            {gradeLabel(child.grade)} {child.stream}
          </p>
        </div>
      </div>
      <div className="profile-grid">
        {facts.map(([label, value]) => (
          <div className="profile-field" key={label}>
            <span className="profile-label">{label}</span>
            <span className="profile-value">
              {value || <span className="muted">—</span>}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

function FeesCard({ child }) {
  const { fees } = child
  return (
    <div className="card">
      <h3>{child.name} — fees</h3>
      <dl className="op-facts">
        <div><dt>Billed this term</dt><dd>{money(fees.billed)}</dd></div>
        <div><dt>Paid</dt><dd>{money(fees.paid)}</dd></div>
        <div><dt>Balance</dt><dd><b>{money(fees.total_balance)}</b></dd></div>
        {fees.next_term_fee && (
          <>
            <div>
              <dt>Term {fees.next_term} {fees.next_year} fee</dt>
              <dd>{money(fees.next_term_fee)}</dd>
            </div>
            <div>
              <dt>To pay next term</dt>
              <dd><b>{money(fees.next_term_total_due)}</b></dd>
            </div>
          </>
        )}
      </dl>
      {fees.next_term_fee && Object.keys(fees.next_term_breakdown || {}).length > 0 && (
        <p className="muted">
          Next term:{' '}
          {Object.entries(fees.next_term_breakdown)
            .map(([head, amount]) => `${head} ${money(amount)}`)
            .join(' · ')}
        </p>
      )}

      {fees.invoices.length === 0 ? (
        <p className="muted">No invoices yet.</p>
      ) : (
        fees.invoices.map((inv) => (
          <div key={inv.id} style={{ marginTop: '0.8rem' }}>
            <p style={{ margin: '0 0 0.3rem' }}>
              <b>Term {inv.term} {inv.year}</b> — {money(inv.due)} billed,{' '}
              {money(inv.paid)} paid,{' '}
              <b>{money(inv.balance)} outstanding</b>{' '}
              <span className={`badge ${inv.status === 'PAID' ? 'online' : 'queued'}`}>
                {inv.status === 'PAID' ? 'Paid' : inv.status === 'PARTIAL' ? 'Part paid' : 'Unpaid'}
              </span>
            </p>
            {Object.keys(inv.breakdown || {}).length > 0 && (
              <p className="muted" style={{ margin: '0 0 0.3rem' }}>
                {Object.entries(inv.breakdown)
                  .map(([head, amount]) => `${head} ${money(amount)}`)
                  .join(' · ')}
              </p>
            )}
            {inv.payments?.length > 0 && (
              <table>
                <thead>
                  <tr><th>Paid on</th><th>Amount</th><th>Method</th><th>Reference</th></tr>
                </thead>
                <tbody>
                  {inv.payments.map((p, i) => (
                    <tr key={i}>
                      <td>{p.paid_on}</td>
                      <td><b>{money(p.amount)}</b></td>
                      <td>{p.method}</td>
                      <td className="muted">{p.reference || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        ))
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
      {tab !== 'Dashboard' && (
        <BackBar title={tab} onBack={() => openTab('Dashboard')} />
      )}

      {tab === 'Dashboard' && (
        <>
          <ChildPicker children={children} selected={child.id} onSelect={setChildId} />
          <PortalHero
            icon="user"
            title={child.name}
            subtitle={`${summary.guardian.name} · ${summary.school} · ${summary.year}`}
            chips={[
              `${gradeLabel(child.grade)}${child.stream ? ` ${child.stream}` : ''}`,
              ...(balance > 0 ? [`${money(child.fees.total_balance)} due`] : ['Fees cleared']),
              ...(child.fees.next_term_fee
                ? [`Term ${child.fees.next_term}: ${money(child.fees.next_term_fee)}`]
                : []),
            ]}
          />
          <ActionGrid>
            <ActionCard icon="user" tone="teal" title="My Child"
              desc="Admission number, UPI, class and class teacher."
              cta="View profile" onOpen={() => openTab('Profile')} />
            <ActionCard icon="clipboard" tone="green" title="Exam Report"
              desc="Detailed results and performance, area by area."
              cta="View results" onOpen={() => openTab('Results')} />
            <ActionCard icon="wallet" tone="orange" title="Fee Balance"
              desc="Payments made and what is still outstanding."
              cta="Check fees" badge={unpaid} onOpen={() => openTab('Fees')} />
            <ActionCard icon="chat" tone="blue" title="Messages"
              desc="Talk to your child's teachers."
              cta="Open messages" onOpen={() => openTab('Messages')} />
            <ActionCard icon="book" tone="teal" title="E-Learning"
              desc="Video lessons, books and past papers for your child's grade."
              cta="Start learning" onOpen={() => openTab('Learn')} />
            <ActionCard icon="bell" tone="purple" title="Announcements"
              desc="Notices and events from the school."
              cta="Read notices" onOpen={() => openTab('Announcements')} />
          </ActionGrid>
        </>
      )}

      {tab === 'Profile' && (
        <>
          <ChildPicker children={children} selected={child.id} onSelect={setChildId} />
          <ProfileCard child={child} />
          <Security />
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

      {tab === 'Learn' && <Learning canCurate={false} />}
      {tab === 'Messages' && <ParentThreads />}
      {tab === 'Announcements' && <Announcements items={summary.announcements} />}

      <BottomNav items={PARENT_NAV} active={tab} onSelect={openTab} />
    </div>
  )
}
