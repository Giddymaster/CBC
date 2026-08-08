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
    const { created, skipped_existing, unfilled } = res.data
    let text = `Created ${created} assignment${created === 1 ? '' : 's'}`
    if (skipped_existing) text += ` (${skipped_existing} already existed)`
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
        <p className="muted">No lessons scheduled for this class yet.</p>
      )}
      {periods.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Day</th>
              {periods.map((p) => (
                <th key={p.id}>
                  P{p.number}
                  <div className="muted">
                    {p.start_time.slice(0, 5)}–{p.end_time.slice(0, 5)}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Object.entries(DAYS).map(([day, label]) => (
              <tr key={day}>
                <td><b>{label}</b></td>
                {periods.map((p) => {
                  const lesson = grid[p.id]?.[day]
                  return <td key={p.id}>{lesson ? areaName(lesson) : ''}</td>
                })}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
