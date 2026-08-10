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
        <h3 style={{ margin: 0 }}>
          Record a payment — {invoice.learner_name} ({invoice.admission_number})
        </h3>
        <button onClick={onClose}>Close</button>
      </div>
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

/** Set what each class is charged, and raise the term's invoices from it. */
function FeeStructures({ onGenerated, onMessage }) {
  const [rows, setRows] = useState([])
  const [form, setForm] = useState({
    grade: 4, term: currentTerm(), year: new Date().getFullYear(),
    amount: '', description: '',
  })
  const load = useCallback(() => {
    apiGet('/api/payments/fee-structures/?page_size=200')
      .then((d) => setRows(d.results || d)).catch(() => setRows([]))
  }, [])
  useEffect(load, [load])

  async function add(e) {
    e.preventDefault()
    if (!(Number(form.amount) > 0)) {
      onMessage('Enter the fee amount.')
      return
    }
    const res = await apiWrite('/api/payments/fee-structures/', {
      ...form, grade: Number(form.grade), term: Number(form.term),
      year: Number(form.year),
    })
    if (res.ok) {
      setForm({ ...form, amount: '', description: '' })
      onMessage('')
      load()
    } else {
      onMessage(res.data?.detail || JSON.stringify(res.data))
    }
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

  return (
    <div className="card">
      <h3>Fee structure</h3>
      <p className="muted">
        What each class pays per term. Set the amount, then raise the invoices —
        every active learner in that grade is billed, and re-running bills only
        newcomers.
      </p>
      <form onSubmit={add}
        style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
        <select value={form.grade} onChange={(e) => setForm({ ...form, grade: e.target.value })}>
          {ALL_GRADES.map((g) => <option key={g} value={g}>{gradeLabel(g)}</option>)}
        </select>
        <select value={form.term} onChange={(e) => setForm({ ...form, term: e.target.value })}>
          {[1, 2, 3].map((t) => <option key={t} value={t}>Term {t}</option>)}
        </select>
        <input type="number" value={form.year} style={{ width: '5.5rem', padding: '0.4rem' }}
          onChange={(e) => setForm({ ...form, year: e.target.value })} />
        <input type="number" min="1" placeholder="Amount (KES)" value={form.amount}
          style={{ width: '9rem', padding: '0.4rem' }}
          onChange={(e) => setForm({ ...form, amount: e.target.value })} />
        <input placeholder="Description (optional)" value={form.description}
          style={{ padding: '0.4rem', minWidth: '12rem' }}
          onChange={(e) => setForm({ ...form, description: e.target.value })} />
        <button className="primary" type="submit">Save fee</button>
      </form>

      {rows.length > 0 && (
        <table>
          <thead>
            <tr><th>Class</th><th>Term</th><th>Amount</th><th>Description</th><th></th></tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td><b>{gradeLabel(r.grade)}</b></td>
                <td>Term {r.term} {r.year}</td>
                <td>{money(r.amount)}</td>
                <td className="muted">{r.description || '—'}</td>
                <td>
                  <button onClick={() => generate(r)}>Raise invoices</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
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

export default function Fees({ grade: fixedGrade }) {
  const [rows, setRows] = useState([])
  const [streams, setStreams] = useState([])
  const [open, setOpen] = useState(null) // invoice being paid
  const [message, setMessage] = useState('')
  const [filters, setFilters] = useState({
    grade: fixedGrade ?? '', stream: '', term: '', year: '', status: '',
  })

  useEffect(() => {
    if (fixedGrade !== null && fixedGrade !== undefined) {
      setFilters((f) => ({ ...f, grade: fixedGrade }))
    }
  }, [fixedGrade])

  const query = [
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

  useEffect(() => {
    if (filters.grade === '') { setStreams([]); return }
    apiGet(`/api/class-groups/?grade=${filters.grade}&page_size=100`)
      .then((d) => setStreams(
        [...new Set((d.results || d).map((c) => c.stream).filter(Boolean))].sort(),
      ))
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
        <p style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
          {(fixedGrade === null || fixedGrade === undefined) && (
            <select value={filters.grade} onChange={setFilter('grade')}>
              <option value="">All grades</option>
              {ALL_GRADES.map((g) => <option key={g} value={g}>{gradeLabel(g)}</option>)}
            </select>
          )}
          {streams.length > 0 && (
            <select value={filters.stream} onChange={setFilter('stream')}>
              <option value="">All streams</option>
              {streams.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          )}
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
