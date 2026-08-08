import { useCallback, useEffect, useState } from 'react'
import { apiGet, apiWrite } from './api.js'
import { gradeLabel, gradeParam } from './format.js'

const DAYS = { 1: 'Mon', 2: 'Tue', 3: 'Wed', 4: 'Thu', 5: 'Fri' }

export default function Timetable({ grade }) {
  const [lessons, setLessons] = useState([])
  const [periods, setPeriods] = useState([])
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    const q = gradeParam(grade)
    apiGet(`/api/timetable/lessons/?page_size=200${q ? `&${q}` : ''}`)
      .then((d) => setLessons(d.results || d))
    apiGet('/api/timetable/periods/').then((d) => setPeriods(d.results || d))
  }, [grade])
  useEffect(load, [load])

  async function generate() {
    setBusy(true)
    setMessage('')
    const result = await apiWrite('/api/timetable/generate/', { clear_existing: true })
    setBusy(false)
    if (result.ok) {
      const { placed, unplaced, lower_grades_skipped } = result.data
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

  // grid[periodId][day] = label
  const grid = {}
  for (const lesson of lessons) {
    grid[lesson.period] = grid[lesson.period] || {}
    grid[lesson.period][lesson.day] = lesson
  }
  const areaName = (lesson) => `${lesson.learning_area_name || lesson.learning_area}`

  return (
    <div className="card">
      <p>
        <button className="primary" onClick={generate} disabled={busy}>
          {busy ? 'Working…' : 'Generate timetable'}
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
        <p className="muted">No lessons scheduled for this class yet.</p>
      )}
      {periods.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Period</th>
              {Object.values(DAYS).map((d) => <th key={d}>{d}</th>)}
            </tr>
          </thead>
          <tbody>
            {periods.map((p) => (
              <tr key={p.id}>
                <td>
                  P{p.number}
                  <div className="muted">{p.start_time.slice(0, 5)}–{p.end_time.slice(0, 5)}</div>
                </td>
                {Object.keys(DAYS).map((day) => {
                  const lesson = grid[p.id]?.[day]
                  return <td key={day}>{lesson ? areaName(lesson) : ''}</td>
                })}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
