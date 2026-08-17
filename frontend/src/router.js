import { useEffect, useState } from 'react'

/**
 * Paths for a tab-based app, without a router library.
 *
 * Each portal owns a base path — /admin, /teacher, /staff, /parent,
 * /operator — and the admin shell's tabs hang off /admin as slugs
 * (/admin/fees, /admin/school-profile). The URL is a second way of saying
 * which tab is open, so the back button, a bookmark and a pasted link all
 * land where they say they will. State stays in React; the address bar is
 * kept honest by two small hooks rather than a routing framework.
 */

export function slugify(name) {
  return String(name)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

/** The current pathname, updating on back/forward and on goTo(). */
export function usePath() {
  const [path, setPath] = useState(window.location.pathname)
  useEffect(() => {
    const onChange = () => setPath(window.location.pathname)
    window.addEventListener('popstate', onChange)
    return () => window.removeEventListener('popstate', onChange)
  }, [])
  return path
}

export function goTo(path, { replace = false } = {}) {
  if (window.location.pathname === path) return
  window.history[replace ? 'replaceState' : 'pushState'](null, '', path)
  // pushState does not fire popstate; fire it ourselves so usePath sees it.
  window.dispatchEvent(new PopStateEvent('popstate'))
}

/** Where each kind of account lives. */
export function basePathFor(me) {
  if (me.is_operator) return '/operator'
  if (me.role === 'PARENT') return '/parent'
  if (me.role === 'TEACHER') return '/teacher'
  if (me.role === 'SUPPORT') return '/staff'
  return '/admin'
}
