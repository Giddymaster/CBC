import { useCallback, useEffect, useRef, useState } from 'react'
import { apiGet, apiUpload, apiWrite } from './api.js'
import BulkImport from './BulkImport.jsx'
import { ALL_GRADES, gradeLabel, todayLocal } from './format.js'
import { LETTERHEAD_CSS, letterheadHtml } from './letterhead.js'

const RESIDENCE = [
  { value: 'DAY', label: 'Day scholar' },
  { value: 'BOARDER', label: 'Boarder' },
]
const TRANSPORT = [
  { value: '', label: '—' },
  { value: 'WALK', label: 'Walks' },
  { value: 'BUS', label: 'School bus' },
  { value: 'PRIVATE', label: 'Private / parent drop-off' },
  { value: 'PUBLIC', label: 'Public transport' },
]
const BLOOD_GROUPS = ['', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']
const RELATIONSHIPS = [
  { value: 'MOTHER', label: 'Mother' },
  { value: 'FATHER', label: 'Father' },
  { value: 'GUARDIAN', label: 'Legal guardian' },
  { value: 'GRANDPARENT', label: 'Grandparent' },
  { value: 'SIBLING', label: 'Sibling' },
  { value: 'OTHER', label: 'Other' },
]

const EMPTY_GUARDIAN = {
  full_name: '', phone: '', alt_phone: '', email: '', relationship: 'MOTHER',
  national_id: '', occupation: '', address: '', is_primary_contact: false,
}

function blankForm(grade) {
  return {
    admission_number: '', upi: '', first_name: '', middle_name: '', last_name: '',
    date_of_birth: '', gender: 'M', grade: grade ?? 1, stream: '',
    birth_certificate_no: '', nationality: 'Kenyan', religion: '',
    admission_date: todayLocal(),
    previous_school: '', previous_grade: '', transfer_reason: '',
    county: '', subcounty: '', ward: '', home_address: '',
    residence: 'DAY', transport: '', bus_route: '',
    blood_group: '', allergies: '', chronic_conditions: '', medication: '',
    nhif_number: '', immunisation_up_to_date: '', special_needs: '',
    emergency_contact_name: '', emergency_contact_phone: '',
    emergency_contact_relationship: '',
    admission_notes: '',
  }
}

function Field({ label, children, hint, wide }) {
  return (
    <label className={`adm-field${wide ? ' adm-wide' : ''}`}>
      <span className="adm-label">{label}</span>
      {children}
      {hint && <span className="adm-hint">{hint}</span>}
    </label>
  )
}

function Section({ title, note, children }) {
  return (
    <fieldset className="adm-section">
      <legend>{title}</legend>
      {note && <p className="adm-note">{note}</p>}
      <div className="adm-grid">{children}</div>
    </fieldset>
  )
}

function GuardianCard({ index, value, onChange, onRemove, canRemove }) {
  const set = (key) => (e) =>
    onChange(index, { ...value, [key]: e.target.value })
  return (
    <div className="adm-guardian">
      <div className="adm-guardian-head">
        <b>Guardian {index + 1}</b>
        <label className="adm-inline">
          <input
            type="checkbox"
            checked={value.is_primary_contact}
            onChange={(e) =>
              onChange(index, { ...value, is_primary_contact: e.target.checked })
            }
          />{' '}
          Primary contact
        </label>
        {canRemove && (
          <button type="button" onClick={() => onRemove(index)}>Remove</button>
        )}
      </div>
      <div className="adm-grid">
        <Field label="Full name">
          <input value={value.full_name} onChange={set('full_name')} />
        </Field>
        <Field label="Relationship">
          <select value={value.relationship} onChange={set('relationship')}>
            {RELATIONSHIPS.map((r) => (
              <option key={r.value} value={r.value}>{r.label}</option>
            ))}
          </select>
        </Field>
        <Field label="Phone" hint="2547XXXXXXXX — used for SMS and M-Pesa">
          <input value={value.phone} onChange={set('phone')} />
        </Field>
        <Field label="Alternative phone">
          <input value={value.alt_phone} onChange={set('alt_phone')} />
        </Field>
        <Field label="ID / passport no">
          <input value={value.national_id} onChange={set('national_id')} />
        </Field>
        <Field label="Occupation">
          <input value={value.occupation} onChange={set('occupation')} />
        </Field>
        <Field label="Email">
          <input type="email" value={value.email} onChange={set('email')} />
        </Field>
        <Field label="Address" wide>
          <input value={value.address} onChange={set('address')} />
        </Field>
      </div>
    </div>
  )
}

// A paper twin of the digital form, for parents filling it at the gate or at
// home. Opens the browser's print dialog — "Save as PDF" makes the download.
function printBlankForm(schoolName, letterhead) {
  const f = (label, wide) =>
    `<div class="f${wide ? ' wide' : ''}"><span>${label}</span><i></i></div>`
  const box = (label) => `<span class="bx">☐ ${label}</span>`
  const area = (label) =>
    `<div class="f wide tall"><span>${label}</span><i></i><i></i></div>`
  const guardian = (n) => `
    <h2>Guardian ${n}</h2>
    <div class="grid">
      ${f('Full name', true)}
      ${f('Relationship')}${f('Phone (2547XXXXXXXX)')}
      ${f('Alternative phone')}${f('ID / passport no')}
      ${f('Occupation')}${f('Email')}
      ${f('Address', true)}
    </div>`
  const html = `<!doctype html><html><head><title>Learner Admission Form</title>
  <style>
    body { font-family: system-ui, sans-serif; font-size: 12px; color: #111;
           max-width: 46rem; margin: 1.2rem auto; padding: 0 1rem; }
    h1 { font-size: 16px; text-align: center; margin: 0; }
    .school { text-align: center; font-size: 14px; font-weight: 700;
              text-transform: uppercase; margin-bottom: 0.2rem; }
    .note { text-align: center; color: #444; margin: 0.3rem 0 1rem; }
    h2 { font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em;
         border-bottom: 1.5px solid #111; padding-bottom: 2px; margin: 1.1rem 0 0.5rem; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.55rem 1.2rem; }
    .f { display: flex; flex-direction: column; gap: 2px; }
    .f.wide { grid-column: 1 / -1; }
    .f span { font-size: 10px; color: #333; }
    .f i { display: block; border-bottom: 1px solid #555; height: 1.1rem; }
    .f.tall i { height: 1.4rem; }
    .bx { margin-right: 1.2rem; }
    .sig { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 1.2rem; margin-top: 1.4rem; }
    @media print { body { margin: 0 auto; } }
    ${LETTERHEAD_CSS}
    .lh { justify-content: center; }
  </style></head><body>
  ${letterhead
    ? letterheadHtml(letterhead)
    : `<div class="school">${schoolName || ''}</div>`}
  <h1>Learner Admission Form</h1>
  <p class="note">Please fill in BLOCK letters. Fields marked * are required.</p>

  <h2>The child</h2>
  <div class="grid">
    ${f('First name *')}${f('Middle name')}
    ${f('Last name *')}${f('Date of birth *')}
    <div class="f"><span>Gender</span><div>${box('Male')}${box('Female')}</div></div>
    ${f('Grade joining (PP1–G12)')}
    ${f('Birth certificate no')}${f('UPI (if issued)')}
    ${f('Nationality')}${f('Religion')}
  </div>

  ${guardian(1)}
  ${guardian(2)}

  <h2>Home and travel</h2>
  <div class="grid">
    ${f('County')}${f('Sub-county')}
    ${f('Ward')}${f('Home address')}
    <div class="f"><span>Day or boarder</span><div>${box('Day scholar')}${box('Boarder')}</div></div>
    <div class="f"><span>How they travel</span>
      <div>${box('Walks')}${box('School bus')}${box('Private')}${box('Public')}</div></div>
  </div>

  <h2>Health — held for the school's duty of care</h2>
  <div class="grid">
    ${f('Blood group')}${f('NHIF number')}
    <div class="f"><span>Immunisation up to date</span><div>${box('Yes')}${box('No')}</div></div>
    ${f('Regular medication')}
    ${area('Allergies (foods, medicines, insect stings)')}
    ${area('Chronic conditions and past serious illnesses (e.g. asthma, epilepsy, sickle cell)')}
    ${area('Special / learning needs (learning support, mobility, vision, hearing)')}
  </div>

  <h2>Emergency contact (other than the guardians above)</h2>
  <div class="grid">
    ${f('Name')}${f('Phone')}
    ${f('Relationship to the child', true)}
  </div>

  <h2>Previous school</h2>
  <div class="grid">
    ${f('School attended')}${f('Grade reached')}
    ${f('Reason for transfer', true)}
  </div>

  <div class="sig">
    ${f('Parent/guardian signature')}${f('Date')}${f('Received by (school)')}
  </div>
  <script>window.onload = function () { window.print() }</script>
  </body></html>`
  const w = window.open('', '_blank')
  if (!w) return
  w.document.write(html)
  w.document.close()
}

export default function Admission({ scope, onAdmitted }) {
  const [access, setAccess] = useState(null)
  const [form, setForm] = useState(() => blankForm(scope))
  const [guardians, setGuardians] = useState([{ ...EMPTY_GUARDIAN, is_primary_contact: true }])
  const [photo, setPhoto] = useState(null)
  const [preview, setPreview] = useState(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [admitted, setAdmitted] = useState(null)
  const fileRef = useRef(null)

  const loadAccess = useCallback(() => {
    apiGet('/api/admissions/access/').then(setAccess).catch(() => setAccess({ can_admit: false }))
  }, [])
  useEffect(loadAccess, [loadAccess])

  // A grade-scoped grant (access.grades) narrows the Grade dropdown, and the
  // form starts on a grade the person may actually admit into.
  const grantGrades = access?.grades?.length ? access.grades : null
  const gradeChoices = grantGrades || ALL_GRADES
  useEffect(() => {
    if (grantGrades && !grantGrades.includes(Number(form.grade))) {
      setForm((f) => ({ ...f, grade: grantGrades[0] }))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- align once per grant
  }, [access])

  // Streams defined for the chosen grade (School (Grades) → Streams). Offered
  // as suggestions; a school without them can still type one.
  const [streams, setStreams] = useState([])
  useEffect(() => {
    apiGet(`/api/school/streams/?grade=${form.grade}`)
      .then((d) => setStreams(d.streams || []))
      .catch(() => setStreams([]))
  }, [form.grade])

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))

  function pickPhoto(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setPhoto(file)
    setPreview(URL.createObjectURL(file))
  }

  function updateGuardian(index, next) {
    setGuardians((list) =>
      list.map((g, i) =>
        // Only one primary contact: ticking a new one unticks the rest.
        i === index ? next : next.is_primary_contact ? { ...g, is_primary_contact: false } : g,
      ),
    )
  }

  async function submit(e) {
    e.preventDefault()
    if (!form.first_name.trim() || !form.last_name.trim()) {
      setMessage('A first name and a last name are required.')
      return
    }
    if (!form.date_of_birth) {
      setMessage('Date of birth is required — it determines the correct grade placement.')
      return
    }
    setBusy(true)
    setMessage('')

    const payload = {
      ...form,
      grade: Number(form.grade),
      immunisation_up_to_date:
        form.immunisation_up_to_date === '' ? null : form.immunisation_up_to_date === 'yes',
      guardians: guardians.filter((g) => g.full_name.trim() && g.phone.trim()),
    }
    if (!payload.upi) delete payload.upi
    if (!payload.admission_number) delete payload.admission_number

    const result = await apiWrite('/api/admissions/', payload)
    if (!result.ok) {
      setBusy(false)
      const detail = result.queued
        ? 'You are offline. An admission creates a permanent record, so it was not queued — please retry when back online.'
        : Object.entries(result.data || {})
            .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(' ') : v}`)
            .join(' · ')
      setMessage(detail || 'Could not admit this learner.')
      return
    }

    const learner = result.data
    if (photo) {
      const body = new FormData()
      body.append('photo', photo)
      await apiUpload(`/api/learners/${learner.id}/photo/`, body)
    }
    setBusy(false)
    setAdmitted(learner)
    onAdmitted?.()
  }

  function admitAnother() {
    setAdmitted(null)
    setForm(blankForm(scope))
    setGuardians([{ ...EMPTY_GUARDIAN, is_primary_contact: true }])
    setPhoto(null)
    setPreview(null)
    setMessage('')
    loadAccess()
  }

  if (!access) return <p className="muted">Loading…</p>

  if (!access.can_admit) {
    return (
      <div className="card">
        <h3>Admissions</h3>
        <p className="muted">
          You do not have admission rights. The school admin can delegate them to you
          from <b>Staff → Admission rights</b>.
        </p>
      </div>
    )
  }

  if (admitted) {
    return (
      <div className="card">
        <h3>{admitted.full_name} admitted</h3>
        <p>
          Admission number <b>{admitted.admission_number}</b> ·{' '}
          {gradeLabel(admitted.grade)}{admitted.stream ? ` ${admitted.stream}` : ''}
        </p>
        <p className="muted">
          The learner is now on the register and will appear in the class list and
          attendance sheets.
        </p>
        <p>
          <button className="primary" onClick={admitAnother}>Admit another learner</button>
        </p>
      </div>
    )
  }

  return (
    <div>
      <div className="card">
        <div className="page-header" style={{ marginBottom: 0 }}>
          <h3 style={{ margin: 0 }}>Admit a new learner</h3>
          <button
            type="button"
            onClick={async () => {
              const me = await apiGet('/api/me/').catch(() => null)
              const profile = await apiGet('/api/my-school/profile/').catch(() => null)
              printBlankForm(me?.school, profile)
            }}
          >
            Download blank form
          </button>
        </div>
        <p className="muted">
          {access.reason}
          {access.note ? ` — ${access.note}` : ''}
          {access.expires_on ? ` · rights expire ${access.expires_on}` : ''}
        </p>
      </div>

      <BulkImport onDone={() => onAdmitted?.()} />

      <form onSubmit={submit}>
        <Section
          title="The child"
          note="Only the name, date of birth and grade are required. Everything else can be filled in later."
        >
          <div className="adm-photo">
            {preview ? (
              <img src={preview} alt="" className="adm-photo-img" />
            ) : (
              <div className="adm-photo-empty">No photo</div>
            )}
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              onChange={pickPhoto}
              style={{ display: 'none' }}
            />
            <button type="button" onClick={() => fileRef.current?.click()}>
              {photo ? 'Change photo' : 'Add photo'}
            </button>
            {photo && (
              <button
                type="button"
                onClick={() => { setPhoto(null); setPreview(null) }}
              >
                Remove
              </button>
            )}
          </div>

          <Field label="First name *">
            <input value={form.first_name} onChange={set('first_name')} />
          </Field>
          <Field label="Middle name">
            <input value={form.middle_name} onChange={set('middle_name')} />
          </Field>
          <Field label="Last name *">
            <input value={form.last_name} onChange={set('last_name')} />
          </Field>
          <Field label="Date of birth *">
            <input type="date" value={form.date_of_birth} onChange={set('date_of_birth')} />
          </Field>
          <Field label="Gender">
            <select value={form.gender} onChange={set('gender')}>
              <option value="M">Male</option>
              <option value="F">Female</option>
            </select>
          </Field>
          <Field label="Grade"
            hint={grantGrades ? 'Limited by your admission rights' : undefined}>
            <select value={form.grade} onChange={set('grade')}>
              {gradeChoices.map((g) => (
                <option key={g} value={g}>{gradeLabel(g)}</option>
              ))}
            </select>
          </Field>
          <Field label="Stream"
            hint={streams.length ? undefined : 'Define streams under School (Grades)'}>
            <input list="admission-streams" value={form.stream} onChange={set('stream')}
              placeholder="e.g. North" />
            <datalist id="admission-streams">
              {streams.map((s) => <option key={s} value={s} />)}
            </datalist>
          </Field>
          <Field
            label="Admission number"
            hint={`Leave blank for ${access.next_admission_number || 'the next number'}`}
          >
            <input value={form.admission_number} onChange={set('admission_number')} />
          </Field>
          <Field label="UPI" hint="NEMIS/KEMIS identifier, if issued">
            <input value={form.upi} onChange={set('upi')} />
          </Field>
          <Field label="Birth certificate no">
            <input
              value={form.birth_certificate_no}
              onChange={set('birth_certificate_no')}
            />
          </Field>
          <Field label="Nationality">
            <input value={form.nationality} onChange={set('nationality')} />
          </Field>
          <Field label="Religion">
            <input value={form.religion} onChange={set('religion')} />
          </Field>
          <Field label="Admission date">
            <input type="date" value={form.admission_date} onChange={set('admission_date')} />
          </Field>
        </Section>

        <Section title="Guardians" note="Whoever the school calls first. At least one phone number.">
          <div className="adm-wide">
            {guardians.map((g, i) => (
              <GuardianCard
                key={i}
                index={i}
                value={g}
                onChange={updateGuardian}
                onRemove={(idx) => setGuardians((l) => l.filter((_, j) => j !== idx))}
                canRemove={guardians.length > 1}
              />
            ))}
            {guardians.length < 4 && (
              <button
                type="button"
                onClick={() => setGuardians((l) => [...l, { ...EMPTY_GUARDIAN }])}
              >
                + Add another guardian
              </button>
            )}
          </div>
        </Section>

        <Section title="Home and travel">
          <Field label="County">
            <input value={form.county} onChange={set('county')} />
          </Field>
          <Field label="Sub-county">
            <input value={form.subcounty} onChange={set('subcounty')} />
          </Field>
          <Field label="Ward">
            <input value={form.ward} onChange={set('ward')} />
          </Field>
          <Field label="Home address" wide>
            <input value={form.home_address} onChange={set('home_address')} />
          </Field>
          <Field label="Day or boarder">
            <select value={form.residence} onChange={set('residence')}>
              {RESIDENCE.map((r) => (
                <option key={r.value} value={r.value}>{r.label}</option>
              ))}
            </select>
          </Field>
          <Field label="How they travel">
            <select value={form.transport} onChange={set('transport')}>
              {TRANSPORT.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </Field>
          {form.transport === 'BUS' && (
            <Field label="Bus route">
              <input value={form.bus_route} onChange={set('bus_route')} />
            </Field>
          )}
        </Section>

        <Section
          title="Health"
          note="Held for the school's duty of care. Staff only — parents never see another family's details, and this is not exported to MoE returns."
        >
          <Field label="Blood group">
            <select value={form.blood_group} onChange={set('blood_group')}>
              {BLOOD_GROUPS.map((b) => (
                <option key={b} value={b}>{b || '—'}</option>
              ))}
            </select>
          </Field>
          <Field label="NHIF number">
            <input value={form.nhif_number} onChange={set('nhif_number')} />
          </Field>
          <Field label="Immunisation up to date">
            <select
              value={form.immunisation_up_to_date}
              onChange={set('immunisation_up_to_date')}
            >
              <option value="">Not stated</option>
              <option value="yes">Yes</option>
              <option value="no">No</option>
            </select>
          </Field>
          <Field label="Allergies" wide hint="Foods, medicines, insect stings">
            <textarea rows="2" value={form.allergies} onChange={set('allergies')} />
          </Field>
          <Field label="Chronic conditions" wide hint="e.g. asthma, epilepsy, sickle cell">
            <textarea rows="2" value={form.chronic_conditions}
              onChange={set('chronic_conditions')} />
          </Field>
          <Field label="Regular medication" wide>
            <textarea rows="2" value={form.medication} onChange={set('medication')} />
          </Field>
          <Field label="Special / learning needs" wide
            hint="Learning support, mobility, vision, hearing">
            <textarea rows="2" value={form.special_needs} onChange={set('special_needs')} />
          </Field>
        </Section>

        <Section
          title="Emergency contact"
          note="Someone other than the guardians above, for when they cannot be reached."
        >
          <Field label="Name">
            <input value={form.emergency_contact_name}
              onChange={set('emergency_contact_name')} />
          </Field>
          <Field label="Phone">
            <input value={form.emergency_contact_phone}
              onChange={set('emergency_contact_phone')} />
          </Field>
          <Field label="Relationship to the child">
            <input value={form.emergency_contact_relationship}
              onChange={set('emergency_contact_relationship')} />
          </Field>
        </Section>

        <Section title="Previous school">
          <Field label="School attended">
            <input value={form.previous_school} onChange={set('previous_school')} />
          </Field>
          <Field label="Grade reached">
            <select value={form.previous_grade} onChange={set('previous_grade')}>
              <option value="">—</option>
              {ALL_GRADES.map((g) => (
                <option key={g} value={gradeLabel(g)}>{gradeLabel(g)}</option>
              ))}
            </select>
          </Field>
          <Field label="Reason for transfer" wide>
            <input value={form.transfer_reason} onChange={set('transfer_reason')} />
          </Field>
          <Field label="Notes" wide>
            <textarea rows="2" value={form.admission_notes} onChange={set('admission_notes')} />
          </Field>
        </Section>

        <div className="card adm-actions">
          <button className="primary" type="submit" disabled={busy}>
            {busy ? 'Admitting…' : 'Admit learner'}
          </button>
          {message && <span className="error">{message}</span>}
        </div>
      </form>
    </div>
  )
}
