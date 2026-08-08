import { useCallback, useEffect, useState } from 'react'
import { apiGet, getToken } from './api.js'
import { ALL_GRADES, gradeLabel } from './format.js'

// August sits in Term 2; the pickers just need a sensible starting point.
function currentTerm() {
  const m = new Date().getMonth() + 1
  return m <= 4 ? 1 : m <= 8 ? 2 : 3
}

async function download(url, filename) {
  const res = await fetch(url, { headers: { Authorization: `Token ${getToken()}` } })
  if (!res.ok) return false
  const blob = await res.blob()
  const href = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = href
  a.download = filename
  a.click()
  URL.revokeObjectURL(href)
  return true
}

/** The whole class on one grid — every learner × every learning area — with
 * Excel and printable report-form sets for the class or the whole school. */
export default function Broadsheet({ grade: fixedGrade }) {
  const [grade, setGrade] = useState(fixedGrade ?? 4)
  const [term, setTerm] = useState(currentTerm())
  const [year, setYear] = useState(new Date().getFullYear())
  const [data, setData] = useState(null)
  const [message, setMessage] = useState('')

  useEffect(() => {
    if (fixedGrade !== null && fixedGrade !== undefined) setGrade(fixedGrade)
  }, [fixedGrade])

  const load = useCallback(() => {
    apiGet(`/api/report-cards/broadsheet/?grade=${grade}&term=${term}&year=${year}`)
      .then(setData)
      .catch(() => setData(null))
  }, [grade, term, year])
  useEffect(load, [load])

  const query = `grade=${grade}&term=${term}&year=${year}`

  async function get(url, filename) {
    setMessage('Preparing…')
    const ok = await download(url, filename)
    setMessage(ok ? '' : 'Could not prepare that file.')
  }

  return (
    <div className="card">
      <p style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
        {(fixedGrade === null || fixedGrade === undefined) && (
          <select value={grade} onChange={(e) => setGrade(Number(e.target.value))}>
            {ALL_GRADES.map((g) => (
              <option key={g} value={g}>{gradeLabel(g)}</option>
            ))}
          </select>
        )}
        <select value={term} onChange={(e) => setTerm(Number(e.target.value))}>
          {[1, 2, 3].map((t) => <option key={t} value={t}>Term {t}</option>)}
        </select>
        <input type="number" value={year} style={{ width: '5.5rem' }}
          onChange={(e) => setYear(Number(e.target.value))} />
        <button className="primary"
          onClick={() => get(
            `/api/report-cards/broadsheet.xlsx?${query}`,
            `broadsheet_${gradeLabel(grade)}_T${term}_${year}.xlsx`,
          )}>
          Download Excel
        </button>
        <button
          onClick={() => get(
            `/api/report-cards/class.pdf?${query}`,
            `report_forms_${gradeLabel(grade)}_T${term}_${year}.pdf`,
          )}>
          Print class report forms
        </button>
        <button
          onClick={() => get(
            `/api/report-cards/class.pdf?term=${term}&year=${year}`,
            `report_forms_school_T${term}_${year}.pdf`,
          )}>
          Print whole school
        </button>
        {message && <span className="muted">{message}</span>}
      </p>

      {data && data.rows.length === 0 && (
        <p className="muted">No learners in {gradeLabel(grade)}.</p>
      )}
      {data && data.rows.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Adm No</th><th>Name</th><th>Stream</th>
              {data.areas.map((a) => <th key={a}>{a}</th>)}
              <th>Mean %</th><th>Rank</th><th></th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r) => (
              <tr key={r.learner}>
                <td className="muted">{r.admission_number}</td>
                <td style={{ whiteSpace: 'nowrap' }}>{r.name}</td>
                <td className="muted">{r.stream || '—'}</td>
                {data.areas.map((a) => {
                  const cell = r.areas[a]
                  return (
                    <td key={a}>
                      {cell ? (
                        <>
                          {cell.percent}%{' '}
                          <span className={`level ${cell.level}`}>{cell.level}</span>
                        </>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                  )
                })}
                <td><b>{r.mean ? `${r.mean}%` : '—'}</b></td>
                <td>{r.rank ?? '—'}</td>
                <td>
                  <button onClick={() => get(
                    `/api/report-card/${r.learner}/pdf/?term=${term}&year=${year}`,
                    `report_${r.admission_number}.pdf`,
                  )}>
                    PDF
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
