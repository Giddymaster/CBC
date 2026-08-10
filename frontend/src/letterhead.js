import { useEffect, useState } from 'react'
import { apiGet } from './api.js'

/**
 * The school's heading for anything that prints from the browser.
 *
 * Each print path used to build its own header, so a school that filled in its
 * postal address saw it on the admission form and nowhere else. One helper, one
 * heading — and the badge uploaded on the School Profile page actually turns up
 * on the paper that leaves the office.
 */

export function useLetterhead() {
  const [profile, setProfile] = useState(null)
  useEffect(() => {
    apiGet('/api/my-school/profile/').then(setProfile).catch(() => setProfile(null))
  }, [])
  return profile
}

export const LETTERHEAD_CSS = `
  .lh { display: flex; align-items: center; gap: 10px;
        border-bottom: 1.5px solid #2b6cb0; padding-bottom: 6px; margin-bottom: 10px; }
  .lh img { width: 54px; height: 54px; object-fit: contain; }
  .lh h1 { font-size: 15px; margin: 0; }
  .lh .motto { font-style: italic; color: #444; }
  .lh .contact { color: #444; font-size: 10px; }
`

/** The school's name, badge and contacts as one HTML block. */
export function letterheadHtml(profile) {
  if (!profile) return ''
  const contact = [profile.postal_address, profile.contact_phone, profile.contact_email]
    .filter(Boolean)
    .join(' · ')
  const badge = profile.logo_url
    ? `<img src="${profile.logo_url}" alt="">`
    : ''
  return `<div class="lh">${badge}<div>
    <h1>${profile.name || ''}</h1>
    ${profile.motto ? `<div class="motto">${profile.motto}</div>` : ''}
    ${contact ? `<div class="contact">${contact}</div>` : ''}
  </div></div>`
}
