import { useCallback, useEffect, useState } from 'react'
import { apiGet, apiWrite, getToken } from './api.js'
import { ALL_GRADES, gradeLabel, todayLocal } from './format.js'

const STATUS_BADGE = { PAID: 'online', PARTIAL: 'queued', UNPAID: 'offline' }
const STATUS_LABEL = { PAID: 'Paid', PARTIAL: 'Part paid', UNPAID: 'Unpaid' }
const METHODS = [
  ['CASH', 'Cash'], ['MPESA', 'M-Pesa'], ['BANK', 'Bank deposit'],
  ['CHEQUE', 'Cheque'], ['BURSARY', 'Bursary / sponsor'], ['WAIVER', 'Waiver'],
]

const money = (n) => `KES ${Number(n || 0).toLocaleString(undefined, {
  minimumFractionDigits: 0, maximumFractionDigits: 0,
})}`

function currentTerm() {
  const m = new Date().getMonth() + 1
  return m <= 4 ? 1 : m <= 8 ? 2 : 3
}

/** Follow DRF pagination — a whole school's invoices outrun one page. */
async function fetchAll(path) {
  const rows = []
  let url = path
  while (url) {
    const d = await apiGet(url)
    rows.push(...(d.results || d))
    url = d.next ? d.next.slice(d.next.indexOf('/api/')) : null
  }
  return rows
}

/** The learner's UPI, editable in place. Blank for a learner admitted before
 * NEMIS issued one; the fees desk is where the parent can finally supply it. */
function UpiCell({ learnerId, upi, onSaved }) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(upi || '')
  const [message, setMessage] = useState('')

  async function save() {
    const next = value.trim()
    if (next === (upi || '')) { setEditing(false); return }
    const res = await apiWrite(`/api/learners/${learnerId}/`, { upi: next },
      { method: 'PATCH' })
    if (res.ok) {
      setEditing(false)
      setMessage('')
      onSaved()
    } else {
      setMessage(res.data?.upi?.[0] || res.data?.detail || 'Could not save the UPI.')
    }
  }

  if (!editing) {
    return (
      <>
        {upi ? <b>{upi}</b> : <span className="muted">Not recorded</span>}{' '}
        <button className="grade-chip" onClick={() => { setValue(upi || ''); setEditing(true) }}>
          {upi ? 'Change' : '+ Add UPI'}
        </button>
      </>
    )
  }
  return (
    <span style={{ display: 'inline-flex', gap: '0.3rem', alignItems: 'center' }}>
      <input autoFocus value={value} placeholder="NEMIS / UPI number"
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') save() }}
        style={{ padding: '0.25rem', width: '10rem' }} />
      <button className="primary" onClick={save}>Save</button>
      <button onClick={() => setEditing(false)}>×</button>
      {message && <span className="error">{message}</span>}
    </span>
  )
}

/** Record one instalment. Families pay what they can, when they can — this
 * takes any amount, any day, by any method, and the invoice re-totals. */
function RecordPayment({ invoice, onDone, onClose }) {
  const [form, setForm] = useState({
    amount: String(Math.max(0, Number(invoice.balance))),
    method: 'CASH',
    paid_on: todayLocal(),
    reference: '',
    note: '',
  })
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  async function save(e) {
    e.preventDefault()
    if (!(Number(form.amount) > 0)) {
      setMessage('Enter the amount received.')
      return
    }
    setBusy(true)
    const res = await apiWrite('/api/payments/payments/', {
      invoice: invoice.id, ...form,
    })
    setBusy(false)
    if (res.ok) onDone()
    else setMessage(res.data?.detail || JSON.stringify(res.data))
  }

  return (
    <div className="card">
      <div className="page-header" style={{ marginBottom: '0.4rem' }}>
        <h3 style={{ margin: 0 }}>Record a payment</h3>
        <button onClick={onClose}>Close</button>
      </div>
      {/* Who is being receipted, in the terms the desk checks: the number the
          parent quotes, the name, the UPI, the class. */}
      <dl className="op-facts">
        <div><dt>Admission no</dt><dd><b>{invoice.admission_number}</b></dd></div>
        <div><dt>Learner</dt><dd>{invoice.learner_name}</dd></div>
        <div>
          <dt>UPI</dt>
          <dd>
            {/* The desk is the one moment a parent is standing there to
                ask — so a missing UPI is captured here, not chased later. */}
            <UpiCell learnerId={invoice.learner} upi={invoice.upi} onSaved={onDone} />
          </dd>
        </div>
        <div><dt>Class</dt><dd>{gradeLabel(invoice.grade)} {invoice.stream}</dd></div>
        <div><dt>Term</dt><dd>Term {invoice.term} {invoice.year}</dd></div>
      </dl>
      <p className="muted">
        {money(invoice.amount_due)} due · {money(invoice.amount_paid)} paid ·{' '}
        <b>{money(invoice.balance)} outstanding</b>
      </p>
      <form onSubmit={save} className="adm-grid" style={{ maxWidth: '44rem' }}>
        <label className="adm-field"><span className="adm-label">Amount received</span>
          <input type="number" min="1" step="1" value={form.amount}
            onChange={set('amount')} /></label>
        <label className="adm-field"><span className="adm-label">Method</span>
          <select value={form.method} onChange={set('method')}>
            {METHODS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select></label>
        <label className="adm-field"><span className="adm-label">Date paid</span>
          <input type="date" value={form.paid_on} onChange={set('paid_on')} /></label>
        <label className="adm-field">
          <span className="adm-label">Reference</span>
          <input value={form.reference} onChange={set('reference')}
            placeholder="M-Pesa code, slip or receipt no" /></label>
        <label className="adm-field adm-wide"><span className="adm-label">Note</span>
          <input value={form.note} onChange={set('note')} /></label>
        <div className="adm-wide">
          <button className="primary" type="submit" disabled={busy}>
            {busy ? 'Saving…' : 'Record payment'}
          </button>
          {message && <span className="error"> {message}</span>}
        </div>
      </form>

      {invoice.payments?.length > 0 && (
        <>
          <h3>Payment history</h3>
          <table>
            <thead>
              <tr><th>Date</th><th>Amount</th><th>Method</th><th>Reference</th>
                <th>Received by</th><th></th></tr>
            </thead>
            <tbody>
              {invoice.payments.map((p) => (
                <tr key={p.id}>
                  <td>{p.paid_on}</td>
                  <td><b>{money(p.amount)}</b></td>
                  <td>{p.method_label}</td>
                  <td className="muted">{p.reference || '—'}</td>
                  <td className="muted">{p.received_by_name || '—'}</td>
                  <td>
                    <button onClick={async () => {
                      if (!window.confirm(`Reverse ${money(p.amount)} of ${p.paid_on}?`)) return
                      await apiWrite(`/api/payments/payments/${p.id}/`, {}, { method: 'DELETE' })
                      onDone()
                    }}>Reverse</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  )
}

/** The fee note as a school prints it: grades down the side, vote heads
 * (tuition, activities, games…) across the top, each cell an amount, the row
 * total at the end. Saving writes one fee structure per grade. */
function FeeStructures({ onGenerated, onMessage }) {
  const [term, setTerm] = useState(currentTerm())
  const [year, setYear] = useState(new Date().getFullYear())
  const [columns, setColumns] = useState([])
  const [rows, setRows] = useState([])
  const [structures, setStructures] = useState([])
  const [busy, setBusy] = useState(false)
  const [newHead, setNewHead] = useState('')

  const load = useCallback(() => {
    apiGet(`/api/payments/fee-structures/grid/?term=${term}&year=${year}`)
      .then((d) => { setColumns(d.columns); setRows(d.rows) })
      .catch(() => { setColumns([]); setRows([]) })
    apiGet(`/api/payments/fee-structures/?term=${term}&year=${year}&page_size=200`)
      .then((d) => setStructures(d.results || d))
      .catch(() => setStructures([]))
  }, [term, year])
  useEffect(load, [load])

  const setCell = (grade, head, value) =>
    setRows((prev) => prev.map((r) => (
      r.grade === grade ? { ...r, breakdown: { ...r.breakdown, [head]: value } } : r
    )))

  const rowTotal = (row) =>
    columns.reduce((sum, head) => sum + (Number(row.breakdown[head]) || 0), 0)
  const columnTotal = (head) =>
    rows.reduce((sum, r) => sum + (Number(r.breakdown[head]) || 0), 0)

  async function save() {
    setBusy(true)
    const res = await apiWrite('/api/payments/fee-structures/grid/', {
      term, year, rows: rows.map((r) => ({ grade: r.grade, breakdown: r.breakdown })),
    })
    setBusy(false)
    onMessage(res.ok
      ? `Fee structure saved for ${res.data.saved} class${res.data.saved === 1 ? '' : 'es'}.`
      : res.data?.detail || 'Could not save the fee structure.')
    if (res.ok) load()
  }

  async function generate(structure) {
    const res = await apiWrite('/api/payments/generate-invoices/', {
      fee_structure: structure.id,
    })
    onMessage(
      res.ok
        ? `Raised ${res.data.created} invoice${res.data.created === 1 ? '' : 's'}`
          + (res.data.skipped_existing
            ? ` (${res.data.skipped_existing} already billed).`
            : '.')
        : res.data?.detail || 'Could not raise invoices.',
    )
    if (res.ok) onGenerated()
  }

  const billable = rows.filter((r) => rowTotal(r) > 0)

  return (
    <div className="card">
      <div className="page-header" style={{ marginBottom: '0.3rem' }}>
        <h3 style={{ margin: 0 }}>Fee structure</h3>
        <span style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
          <select value={term} onChange={(e) => setTerm(Number(e.target.value))}>
            {[1, 2, 3].map((t) => <option key={t} value={t}>Term {t}</option>)}
          </select>
          <input type="number" value={year} style={{ width: '5.5rem', padding: '0.4rem' }}
            onChange={(e) => setYear(Number(e.target.value))} />
          <button className="primary" onClick={save} disabled={busy}>
            {busy ? 'Saving…' : 'Save fee structure'}
          </button>
        </span>
      </div>
      <p className="muted">
        What each class pays this term, broken down by vote head. Leave a class
        blank if it is not charged. Save, then raise that class's invoices —
        every active learner is billed, and re-running bills only newcomers.
      </p>

      <table>
        <thead>
          <tr>
            <th>Class</th>
            {columns.map((head) => <th key={head}>{head}</th>)}
            <th>Total</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const total = rowTotal(row)
            const structure = structures.find((s) => s.grade === row.grade)
            return (
              <tr key={row.grade}>
                <td><b>{row.label}</b></td>
                {columns.map((head) => (
                  <td key={head}>
                    <input
                      type="number" min="0" step="50"
                      value={row.breakdown[head] ?? ''}
                      onChange={(e) => setCell(row.grade, head, e.target.value)}
                      style={{ width: '5.5rem', padding: '0.2rem' }}
                    />
                  </td>
                ))}
                <td><b>{total ? money(total) : <span className="muted">—</span>}</b></td>
                <td style={{ whiteSpace: 'nowrap' }}>
                  {structure && (
                    <button onClick={() => generate(structure)}>Raise invoices</button>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
        <tfoot>
          <tr>
            <td><b>All classes</b></td>
            {columns.map((head) => (
              <td key={head} className="muted">
                {columnTotal(head) ? money(columnTotal(head)) : '—'}
              </td>
            ))}
            <td colSpan="2" />
          </tr>
        </tfoot>
      </table>

      <p style={{ display: 'flex', gap: '0.4rem', alignItems: 'center', flexWrap: 'wrap' }}>
        <input value={newHead} placeholder="Another vote head e.g. Uniform"
          style={{ padding: '0.35rem' }}
          onChange={(e) => setNewHead(e.target.value)} />
        <button onClick={() => {
          const head = newHead.trim()
          if (head && !columns.includes(head)) setColumns([...columns, head])
          setNewHead('')
        }}>+ Add column</button>
        <span className="muted">
          {billable.length} class{billable.length === 1 ? '' : 'es'} charged this term
        </span>
      </p>
    </div>
  )
}

/** A printable copy of exactly what is on screen — the filtered register. */
function printRegister(title, rows, totals) {
  const cells = rows.map((r) => `<tr>
    <td>${r.admission_number || ''}</td><td>${r.learner_name || ''}</td>
    <td>${gradeLabel(r.grade)} ${r.stream || ''}</td>
    <td>T${r.term || ''} ${r.year || ''}</td>
    <td class="n">${Number(r.amount_due).toLocaleString()}</td>
    <td class="n">${Number(r.amount_paid).toLocaleString()}</td>
    <td class="n">${Number(r.balance).toLocaleString()}</td>
    <td>${STATUS_LABEL[r.status] || r.status}</td></tr>`).join('')
  const html = `<!doctype html><html><head><title>${title}</title><style>
    body { font-family: system-ui, sans-serif; font-size: 11px; margin: 1.2rem; }
    h1 { font-size: 15px; margin: 0 0 0.2rem; }
    .sub { color: #444; margin: 0 0 0.8rem; }
    table { width: 100%; border-collapse: collapse; }
    th, td { border: 1px solid #999; padding: 3px 5px; text-align: left; }
    th { background: #eee; }
    .n { text-align: right; }
    tfoot td { font-weight: bold; background: #f4f4f4; }
    @media print { body { margin: 0.5rem; } }
  </style></head><body>
  <h1>${title}</h1>
  <p class="sub">${rows.length} learners · printed ${new Date().toLocaleDateString()}</p>
  <table><thead><tr>
    <th>Adm No</th><th>Learner</th><th>Class</th><th>Term</th>
    <th class="n">Fee due</th><th class="n">Paid</th><th class="n">Balance</th><th>Status</th>
  </tr></thead><tbody>${cells}</tbody>
  <tfoot><tr><td colspan="4">Totals</td>
    <td class="n">${totals.due.toLocaleString()}</td>
    <td class="n">${totals.paid.toLocaleString()}</td>
    <td class="n">${totals.balance.toLocaleString()}</td><td></td></tr></tfoot>
  </table>
  <script>window.onload = function () { window.print() }</script>
  </body></html>`
  const w = window.open('', '_blank')
  if (!w) return
  w.document.write(html)
  w.document.close()
}

/** The fees desk's front door: a parent quotes an admission number, and the
 * register narrows to that learner with their name and UPI confirmed. */
function AdmissionLookup({ value, onFound, onClear, onMessage }) {
  const [adm, setAdm] = useState('')
  const [busy, setBusy] = useState(false)

  async function find(e) {
    e.preventDefault()
    const number = adm.trim()
    if (!number) return
    setBusy(true)
    const d = await apiGet(
      `/api/learners/?admission_number=${encodeURIComponent(number)}`,
    ).catch(() => null)
    setBusy(false)
    const learner = (d?.results || d || [])[0]
    if (!learner) {
      onMessage(`No learner with admission number ${number}.`)
      return
    }
    onMessage('')
    onFound(learner)
    setAdm('')
  }

  if (value) {
    return (
      <p className="op-creds handover" style={{ display: 'flex', gap: '0.6rem',
        alignItems: 'center', flexWrap: 'wrap' }}>
        <b>{value.admission_number}</b> · {value.full_name} · UPI{' '}
        <b>{value.upi || '—'}</b> · {gradeLabel(value.grade)} {value.stream}
        <button onClick={onClear} style={{ marginLeft: 'auto' }}>
          Show the whole register
        </button>
      </p>
    )
  }
  return (
    <form onSubmit={find}
      style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
      <label className="muted" style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
        Admission no
        <input value={adm} onChange={(e) => setAdm(e.target.value)}
          placeholder="e.g. ADM0126" style={{ padding: '0.4rem', width: '10rem' }} />
      </label>
      <button className="primary" type="submit" disabled={busy}>
        {busy ? 'Finding…' : 'Find learner'}
      </button>
      <span className="muted">
        Look a family up by the number the parent quotes.
      </span>
    </form>
  )
}

export default function Fees({ grade: fixedGrade }) {
  const [rows, setRows] = useState([])
  const [streams, setStreams] = useState([])
  const [open, setOpen] = useState(null) // invoice being paid
  const [learner, setLearner] = useState(null) // looked up by admission no
  const [message, setMessage] = useState('')
  const [filters, setFilters] = useState({
    grade: fixedGrade ?? '', stream: '', term: '', year: '', status: '',
  })

  useEffect(() => {
    if (fixedGrade !== null && fixedGrade !== undefined) {
      setFilters((f) => ({ ...f, grade: fixedGrade }))
    }
  }, [fixedGrade])

  // A looked-up learner overrides the class filters — the desk is dealing
  // with that one family until it clears.
  const query = learner
    ? `learner=${learner.id}`
    : [
        filters.grade !== '' && `learner__grade=${filters.grade}`,
        filters.stream && `learner__stream=${encodeURIComponent(filters.stream)}`,
        filters.term && `fee_structure__term=${filters.term}`,
        filters.year && `fee_structure__year=${filters.year}`,
        filters.status && `status=${filters.status}`,
      ].filter(Boolean).join('&')

  const load = useCallback(() => {
    fetchAll(`/api/payments/invoices/?page_size=500${query ? `&${query}` : ''}`)
      .then(setRows)
      .catch(() => setRows([]))
  }, [query])
  useEffect(load, [load])

  // Streams the learners are really in, not only the class groups somebody
  // remembered to create.
  useEffect(() => {
    const q = filters.grade === '' ? '' : `?grade=${filters.grade}`
    apiGet(`/api/school/streams/${q}`)
      .then((d) => setStreams(d.streams || []))
      .catch(() => setStreams([]))
  }, [filters.grade])

  // Keep the open dialog in step with the reloaded rows.
  useEffect(() => {
    if (open) setOpen(rows.find((r) => r.id === open.id) || null)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- follow by id only
  }, [rows])

  const totals = rows.reduce((acc, r) => ({
    due: acc.due + Number(r.amount_due),
    paid: acc.paid + Number(r.amount_paid),
    balance: acc.balance + Number(r.balance),
  }), { due: 0, paid: 0, balance: 0 })

  const setFilter = (k) => (e) => setFilters({ ...filters, [k]: e.target.value })
  const title = 'Fee register'
    + (filters.grade !== '' ? ` — ${gradeLabel(Number(filters.grade))}` : '')
    + (filters.stream ? ` ${filters.stream}` : '')
    + (filters.term ? ` · Term ${filters.term}` : '')
    + (filters.year ? ` ${filters.year}` : '')

  async function downloadExcel() {
    const res = await fetch(`/api/payments/register.xlsx?${query}`, {
      headers: { Authorization: `Token ${getToken()}` },
    })
    if (!res.ok) { setMessage('Could not prepare the workbook.'); return }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'fee_register.xlsx'
    a.click()
    URL.revokeObjectURL(url)
  }

  if (open) {
    return (
      <RecordPayment
        invoice={open}
        onDone={() => { setMessage(''); load() }}
        onClose={() => setOpen(null)}
      />
    )
  }

  return (
    <div>
      <FeeStructures onGenerated={load} onMessage={setMessage} />

      <div className="card">
        <AdmissionLookup
          value={learner}
          onFound={setLearner}
          onClear={() => setLearner(null)}
          onMessage={setMessage}
        />
        <p style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
          {!learner && (fixedGrade === null || fixedGrade === undefined) && (
            <select value={filters.grade} onChange={setFilter('grade')}>
              <option value="">All grades</option>
              {ALL_GRADES.map((g) => <option key={g} value={g}>{gradeLabel(g)}</option>)}
            </select>
          )}
          {!learner && streams.length > 0 && (
            <select value={filters.stream} onChange={setFilter('stream')}>
              <option value="">All streams</option>
              {streams.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          )}
          {!learner && (
            <>
              <select value={filters.term} onChange={setFilter('term')}>
                <option value="">All terms</option>
                {[1, 2, 3].map((t) => <option key={t} value={t}>Term {t}</option>)}
              </select>
              <input type="number" placeholder="Year" value={filters.year}
                style={{ width: '5.5rem', padding: '0.4rem' }} onChange={setFilter('year')} />
              <select value={filters.status} onChange={setFilter('status')}>
                <option value="">Any status</option>
                <option value="UNPAID">Unpaid</option>
                <option value="PARTIAL">Part paid</option>
                <option value="PAID">Paid</option>
              </select>
            </>
          )}
          <button className="primary" onClick={downloadExcel}>Download Excel</button>
          <button onClick={() => printRegister(title, rows, totals)}>Print</button>
        </p>
        {message && <p className="muted">{message}</p>}
        <p className="muted">
          {rows.length} learners · {money(totals.due)} billed · {money(totals.paid)} collected ·{' '}
          <b>{money(totals.balance)} outstanding</b>
        </p>

        {rows.length === 0 ? (
          <p className="muted">
            No invoices here yet — set a fee above and click <b>Raise invoices</b>.
          </p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Learner</th><th>Class</th><th>Term</th>
                <th>Fee due</th><th>Paid</th><th>Balance</th><th>Status</th><th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <b>{r.admission_number}</b>
                    <div>{r.learner_name}</div>
                  </td>
                  <td>{gradeLabel(r.grade)} {r.stream}</td>
                  <td className="muted">T{r.term} {r.year}</td>
                  <td>{money(r.amount_due)}</td>
                  <td>{money(r.amount_paid)}</td>
                  <td><b>{money(r.balance)}</b></td>
                  <td>
                    <span className={`badge ${STATUS_BADGE[r.status]}`}>
                      {STATUS_LABEL[r.status] || r.status}
                    </span>
                  </td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <button className="primary" onClick={() => setOpen(r)}>
                      {r.status === 'PAID' ? 'Statement' : 'Record payment'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
