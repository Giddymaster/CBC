import { useCallback, useEffect, useState } from 'react'
import { apiGet, apiWrite } from './api.js'
import { gradeLabel, gradeParam, subjectColor } from './format.js'

const DAYS = { 1: 'Mon', 2: 'Tue', 3: 'Wed', 4: 'Thu', 5: 'Fri' }

/** Periods interleaved with the gaps between them: a 30-minute gap is a
 * break, an hour is lunch — read straight off the period times, so custom
 * school days get their gaps too. */
function buildColumns(periods) {
  const minutes = (t) => Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5))
  const columns = []
  periods.forEach((p, i) => {
    columns.push({ type: 'period', period: p })
    const next = periods[i + 1]
    if (next) {
      const gap = minutes(next.start_time) - minutes(p.end_time)
      if (gap >= 10) {
        columns.push({
          type: 'gap',
          label: gap >= 45 ? 'Lunch' : 'Break',
          time: `${p.end_time.slice(0, 5)}–${next.start_time.slice(0, 5)}`,
          key: `gap-${p.id}`,
        })
      }
    }
  })
  return columns
}

/** Follow DRF pagination until every row is in hand — a full school week is
 * bigger than any single page. */
async function fetchAllLessons(query) {
  const rows = []
  let url = `/api/timetable/lessons/?page_size=500${query ? `&${query}` : ''}`
  while (url) {
    const d = await apiGet(url)
    rows.push(...(d.results || d))
    url = d.next ? d.next.slice(d.next.indexOf('/api/')) : null
  }
  return rows
}

export default function Timetable({ grade }) {
  const [lessons, setLessons] = useState([])
  const [periods, setPeriods] = useState([])
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    fetchAllLessons(gradeParam(grade)).then(setLessons).catch(() => setLessons([]))
    apiGet('/api/timetable/periods/').then((d) => setPeriods(d.results || d))
  }, [grade])
  useEffect(load, [load])

  async function generate() {
    setBusy(true)
    setMessage('')
    const result = await apiWrite('/api/timetable/generate/', { clear_existing: true })
    setBusy(false)
    if (result.ok) {
      const { placed, unplaced, requirements, lower_grades_skipped } = result.data
      if (!requirements) {
        setMessage(
          'Nothing to schedule: no teaching assignments exist for Grades 4–9 yet. '
          + 'Click "Auto-assign teachers" to build them from teacher subjects and '
          + 'phases, or assign per grade under School (Grades).',
        )
        return
      }
      setMessage(
        `Placed ${placed} lessons.` +
          (unplaced.length ? ` Could not place: ${unplaced.join('; ')}` : ' No clashes.') +
          (lower_grades_skipped
            ? ` ${lower_grades_skipped} lower-grade assignment${lower_grades_skipped === 1 ? '' : 's'}` +
              ' not scheduled — PP1–G3 classes stay with their class teacher all day.'
            : ''),
      )
      load()
    } else {
      setMessage('Generation failed — are requirements and periods configured?')
    }
  }

  async function autoAssign() {
    setBusy(true)
    setMessage('')
    const res = await apiWrite('/api/timetable/assignments/auto/', {})
    setBusy(false)
    if (!res.ok) {
      setMessage(res.data?.detail || 'Could not auto-assign.')
      return
    }
    const { created, skipped_existing, rebalanced, unfilled } = res.data
    let text = `Created ${created} assignment${created === 1 ? '' : 's'}`
    if (rebalanced) {
      text += `, rebalanced ${rebalanced} so every class's week is full`
    }
    if (skipped_existing) text += ` (${skipped_existing} already right)`
    text += '.'
    if (unfilled.length) {
      const sample = unfilled.slice(0, 5)
        .map((u) => `${gradeLabel(u.grade)}${u.stream ? ` ${u.stream}` : ''} ${u.area}`)
        .join('; ')
      text += ` ${unfilled.length} class-subject${unfilled.length === 1 ? '' : 's'} have no `
        + `qualified teacher: ${sample}${unfilled.length > 5 ? '…' : ''} — give a teacher `
        + 'that subject (and the right phase) on the Staff page, then run this again.'
    } else if (created) {
      text += ' Now click Generate timetable.'
    }
    setMessage(text)
  }

  async function loadStandardDay() {
    setBusy(true)
    const res = await apiWrite('/api/timetable/periods/seed-standard/', {})
    setBusy(false)
    setMessage(
      res.ok
        ? 'Standard day loaded: 2 lessons 07:30–09:00, break, 2 lessons 09:30–11:00, '
          + 'break, 2 lessons 11:30–13:00, lunch, 3 lessons 14:00–16:00, then preps to 17:00.'
        : res.data?.detail || 'Could not load the standard day.',
    )
    load()
  }

  // The classes on the chart — every grade+stream that has lessons, in order.
  const classes = [...new Set(lessons.map((l) => `${l.grade}|${l.stream}`))]
    .map((key) => {
      const [g, s] = key.split('|')
      return { grade: Number(g), stream: s }
    })
    .sort((a, b) => a.grade - b.grade || a.stream.localeCompare(b.stream))

  // cell[day|grade|stream|period] -> lesson
  const cell = {}
  for (const l of lessons) {
    cell[`${l.day}|${l.grade}|${l.stream}|${l.period}`] = l
  }
  const classLabel = (c) => `${gradeLabel(c.grade)}${c.stream ? ` ${c.stream}` : ''}`

  return (
    <div className="card">
      <p>
        <button className="primary" onClick={generate} disabled={busy}>
          {busy ? 'Working…' : 'Generate timetable'}
        </button>{' '}
        <button onClick={autoAssign} disabled={busy}>
          Auto-assign teachers
        </button>{' '}
        <button onClick={loadStandardDay} disabled={busy}>
          Load the standard day
        </button>{' '}
        <span className="muted">
          {grade === null || grade === undefined
            ? 'Grades 4–9, from the teaching assignments'
            : `${gradeLabel(grade)} — regenerates from the teaching assignments`}
          {' · PP1–G3 stay with their class teacher all day'}
        </span>
      </p>
      {message && <p className="muted">{message}</p>}
      {periods.length === 0 && (
        <p className="muted">
          No periods defined yet — load the standard day above, or add your own
          under Timetable periods.
        </p>
      )}
      {periods.length > 0 && lessons.length === 0 && (
        <p className="muted">No lessons scheduled yet.</p>
      )}
      {periods.length > 0 && classes.length > 0 && (() => {
        const columns = buildColumns(periods)
        return (
          <table>
            <thead>
              <tr>
                <th>Day</th>
                <th>Class</th>
                {columns.map((col) =>
                  col.type === 'period' ? (
                    <th key={col.period.id}>
                      P{col.period.number}
                      <div className="muted">
                        {col.period.start_time.slice(0, 5)}–{col.period.end_time.slice(0, 5)}
                      </div>
                    </th>
                  ) : (
                    <th key={col.key} className="tt-gap">
                      {col.label}
                      <div className="muted">{col.time}</div>
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {Object.entries(DAYS).map(([day, label]) =>
                classes.map((c, i) => (
                  <tr key={`${day}-${c.grade}-${c.stream}`}
                    className={i === 0 ? 'day-start' : undefined}>
                    {i === 0 && (
                      <td rowSpan={classes.length} className="day-cell"><b>{label}</b></td>
                    )}
                    <td style={{ whiteSpace: 'nowrap' }}>{classLabel(c)}</td>
                    {columns.map((col) => {
                      if (col.type === 'gap') {
                        return <td key={col.key} className="tt-gap" />
                      }
                      const l = cell[`${day}|${c.grade}|${c.stream}|${col.period.id}`]
                      const name = l ? (l.learning_area_name || l.learning_area) : ''
                      return (
                        <td
                          key={col.period.id}
                          title={l?.teacher_name || ''}
                          style={name ? { background: subjectColor(String(name)) } : undefined}
                        >
                          {name}
                        </td>
                      )
                    })}
                  </tr>
                )),
              )}
            </tbody>
          </table>
        )
      })()}
    </div>
  )
}
