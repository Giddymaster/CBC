/**
 * The staff-portal look: a hero banner, big tap-friendly action cards, and a
 * phone bottom tab bar. Shared by the teacher and support-staff portals so the
 * two dashboards stay siblings, not cousins.
 */

const PATHS = {
  grid: (
    <>
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </>
  ),
  calendar: (
    <>
      <rect x="3" y="4" width="18" height="18" rx="2" />
      <line x1="16" y1="2" x2="16" y2="6" />
      <line x1="8" y1="2" x2="8" y2="6" />
      <line x1="3" y1="10" x2="21" y2="10" />
    </>
  ),
  pencil: (
    <path d="M17 3a2.8 2.8 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z" />
  ),
  check: (
    <>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M8 12l3 3 5-6" />
    </>
  ),
  book: (
    <>
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
    </>
  ),
  clipboard: (
    <>
      <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
      <rect x="8" y="2" width="8" height="4" rx="1" />
      <line x1="8" y1="11" x2="16" y2="11" />
      <line x1="8" y1="15" x2="14" y2="15" />
    </>
  ),
  chart: (
    <>
      <line x1="4" y1="20" x2="20" y2="20" />
      <rect x="6" y="11" width="3" height="9" rx="0.5" />
      <rect x="11" y="6" width="3" height="14" rx="0.5" />
      <rect x="16" y="14" width="3" height="6" rx="0.5" />
    </>
  ),
  star: (
    <path d="M12 2l3.1 6.3 6.9 1-5 4.9 1.2 6.8L12 17.8 5.8 21l1.2-6.8-5-4.9 6.9-1L12 2z" />
  ),
  chat: (
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v10z" />
  ),
  file: (
    <>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6" />
      <line x1="8" y1="13" x2="16" y2="13" />
      <line x1="8" y1="17" x2="13" y2="17" />
    </>
  ),
  user: (
    <>
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </>
  ),
  users: (
    <>
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </>
  ),
  plus: (
    <>
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="8" x2="12" y2="16" />
      <line x1="8" y1="12" x2="16" y2="12" />
    </>
  ),
  wallet: (
    <>
      <path d="M21 7H5a2 2 0 0 1 0-4h14v4" />
      <path d="M3 5v14a2 2 0 0 0 2 2h16V7" />
      <circle cx="16.5" cy="14" r="1.5" />
    </>
  ),
  bell: (
    <>
      <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.7 21a2 2 0 0 1-3.4 0" />
    </>
  ),
}

export function Icon({ name, size = 24 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round" aria-hidden="true">
      {PATHS[name] || PATHS.grid}
    </svg>
  )
}

/** The blue banner at the top of a portal: who you are, where, and the numbers
 * that matter today. */
export function PortalHero({ icon = 'user', title, subtitle, chips = [] }) {
  return (
    <div className="hero">
      <span className="hero-icon"><Icon name={icon} size={28} /></span>
      <div className="hero-text">
        <h2>{title}</h2>
        {subtitle && <p>{subtitle}</p>}
        {chips.length > 0 && (
          <div className="hero-chips">
            {chips.map((c) => <span key={c} className="hero-chip">{c}</span>)}
          </div>
        )}
      </div>
    </div>
  )
}

/** One big tappable card: pastel icon tile, what it is, why you'd tap it. */
export function ActionCard({ icon, tone = 'blue', title, desc, cta, badge = 0, onOpen }) {
  return (
    <button type="button" className="action-card" onClick={onOpen}>
      <span className={`action-tile tile-${tone}`}><Icon name={icon} /></span>
      <span className="action-body">
        <span className="action-title">
          {title}
          {badge > 0 && <span className="action-badge">{badge}</span>}
        </span>
        <span className="action-desc">{desc}</span>
        <span className={`action-cta cta-${tone}`}>{cta} →</span>
      </span>
    </button>
  )
}

export function ActionGrid({ children }) {
  return <div className="action-grid">{children}</div>
}

/** Phone-only bottom tab bar (CSS hides it on desktop). `items` are
 * { key, label, icon }; `active`/`onSelect` speak the portal's tab names. */
export function BottomNav({ items, active, onSelect }) {
  return (
    <nav className="bottom-nav">
      {items.map((item) => (
        <button
          key={item.key}
          type="button"
          className={active === item.key ? 'active' : ''}
          onClick={() => onSelect(item.key)}
        >
          <Icon name={item.icon} size={22} />
          <span>{item.label}</span>
        </button>
      ))}
    </nav>
  )
}
