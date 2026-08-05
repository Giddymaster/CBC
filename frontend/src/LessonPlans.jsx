import { useCallback, useEffect, useState } from 'react'
import { apiGet, apiWrite } from './api.js'
import { gradeLabel } from './format.js'

const BLANK = {
  week: 1, lesson_number: 1, strand: '', sub_strand: '',
  learning_outcomes: '', resources: '',
}

/** Lesson plans, reached through the scheme of work they belong to. */
export default function LessonPlans({ summary }) {
  const schemes = summary?.schemes_of_work || []
  const [schemeId, setSchemeId] = useState(schemes[0]?.id || '')
  const [data, setData] = useState(null)
  const [form, setForm] = useState(BLANK)
  const [message, setMessage] = useState('')

  const load = useCallback(() => {
    if (!schemeId) return
    apiGet(`/api/schemes-of-work/${schemeId}/lesson-plans/`)
      .then(setData)
      .catch(() => setData(null))
  }, [schemeId])
  useEffect(load, [load])

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))

  async function save(e) {
    e.preventDefault()
    if (!form.learning_outcomes.trim()) {
      setMessage('A lesson plan needs its learning outcomes.')
      return
    }
    const res = await apiWrite(`/api/schemes-of-work/${schemeId}/lesson-plans/`, {
      ...form,
      week: Number(form.week),
      lesson_number: Number(form.lesson_number),
    })
    setMessage(res.ok ? 'Lesson plan saved.' : `Failed: ${JSON.stringify(res.data)}`)
    if (res.ok) load()
  }

  /** Fill the form from the scheme's own week, so the plan follows the plan. */
  function prefill(week, lesson) {
    setForm({
      week: week.week,
      lesson_number: lesson.lesson,
      strand: lesson.strand || '',
      sub_strand: lesson.sub_strand || '',
      learning_outcomes: (lesson.learning_outcomes || []).join('\n'),
      resources: lesson.resources || '',
    })
    setMessage('Filled from the scheme — edit and save.')
  }

  if (schemes.length === 0) {
    return (
      <div className="card">
        <h3>Lesson plans</h3>
        <p className="muted">
          A lesson plan belongs to a scheme of work. Create or generate a scheme
          first, then plan its lessons here.
        </p>
      </div>
    )
  }

  return (
    <div>
      <div className="card">
        <h3>Lesson plans</h3>
        <p>
          <select value={schemeId} onChange={(e) => setSchemeId(Number(e.target.value))}>
            {schemes.map((s) => (
              <option key={s.id} value={s.id}>
                {s.learning_area} {gradeLabel(s.grade)} · Term {s.term} {s.year}
              </option>
            ))}
          </select>
        </p>

        <form onSubmit={save} className="adm-grid">
          <label className="adm-field">
            <span className="adm-label">Week</span>
            <input type="number" min="1" value={form.week} onChange={set('week')} />
          </label>
          <label className="adm-field">
            <span className="adm-label">Lesson</span>
            <input type="number" min="1" value={form.lesson_number}
              onChange={set('lesson_number')} />
          </label>
          <label className="adm-field">
            <span className="adm-label">Strand</span>
            <input value={form.strand} onChange={set('strand')} />
          </label>
          <label className="adm-field">
            <span className="adm-label">Sub-strand</span>
            <input value={form.sub_strand} onChange={set('sub_strand')} />
          </label>
          <label className="adm-field adm-wide">
            <span className="adm-label">Learning outcomes</span>
            <textarea rows="3" value={form.learning_outcomes}
              onChange={set('learning_outcomes')} />
          </label>
          <label className="adm-field adm-wide">
            <span className="adm-label">Resources</span>
            <input value={form.resources} onChange={set('resources')} />
          </label>
          <div className="adm-wide">
            <button className="primary" type="submit">Save lesson plan</button>
            {message && <span className="muted"> {message}</span>}
          </div>
        </form>
      </div>

      {data?.weeks?.length > 0 && (
        <div className="card">
          <h3>From the scheme</h3>
          <p className="muted">Click a lesson to start its plan.</p>
          {data.weeks.map((week) => (
            <div key={week.week} style={{ marginBottom: '0.5rem' }}>
              <b>Week {week.week}</b>{' '}
              {(week.lessons || []).map((lesson) => (
                <button
                  key={lesson.lesson}
                  onClick={() => prefill(week, lesson)}
                  className="grade-chip"
                  style={{ marginRight: '0.3rem' }}
                >
                  L{lesson.lesson} {lesson.sub_strand || lesson.strand || ''}
                </button>
              ))}
            </div>
          ))}
        </div>
      )}

      {data?.lesson_plans?.length > 0 && (
        <div className="card">
          <h3>Planned ({data.lesson_plans.length})</h3>
          <table>
            <thead>
              <tr><th>Week</th><th>Lesson</th><th>Strand</th><th>Outcomes</th><th>Resources</th></tr>
            </thead>
            <tbody>
              {data.lesson_plans.map((p) => (
                <tr key={p.id}>
                  <td>{p.week}</td>
                  <td>{p.lesson_number}</td>
                  <td>
                    {p.strand}
                    {p.sub_strand && <div className="muted">{p.sub_strand}</div>}
                  </td>
                  <td style={{ whiteSpace: 'pre-wrap' }}>{p.learning_outcomes}</td>
                  <td className="muted">{p.resources || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
