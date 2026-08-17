import { useEffect, useState } from 'react'

/**
 * Paths for a tab-based app, without a router library.
 *
 * The school leads the path: shulenest.com/<school>/admin/fees,
 * /<school>/teacher, /<school>/parent. The school segment is the tenant's URL
 * handle (its slug), so the address bar names which school you are in — the
 * data still comes from the signed-in account, the slug is the label. The
 * platform operator has no school and lives at /operator.
 *
 * The URL is a second way of saying which portal and tab are open, so the back
 * button, a bookmark and a pasted link all land where they say. State stays in
 * React; two small hooks keep the address bar honest rather than a framework.
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

/** The portal segment for an account: admin / teacher / staff / parent / operator. */
export function portalFor(me) {
  if (me.is_operator) return 'operator'
  if (me.role === 'PARENT') return 'parent'
  if (me.role === 'TEACHER') return 'teacher'
  if (me.role === 'SUPPORT') return 'staff'
  return 'admin'
}

/**
 * Where an account lives, school first. The operator has no school, so it stays
 * at /operator; everyone else is /<school>/<portal>. A school user without a
 * slug (older account, mid-migration) falls back to no school segment rather
 * than a broken /undefined/.
 */
export function basePathFor(me) {
  const portal = portalFor(me)
  if (portal === 'operator') return '/operator'
  return me.school_slug ? `/${me.school_slug}/${portal}` : `/${portal}`
}
