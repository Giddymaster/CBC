import { useCallback, useEffect, useState } from 'react'
import Admission from './Admission.jsx'
import { PdRecords, PeerReview, TeacherDetail } from './Analysis.jsx'
import { StaffParentThreads } from './ParentMessages.jsx'
import { apiGet, apiWrite } from './api.js'
import Attendance from './Attendance.jsx'
import { gradeLabel } from './format.js'
import LessonPlans from './LessonPlans.jsx'
import TeacherSchemes from './Schemes.jsx'
import MyTeam from './MyTeam.jsx'
import { MyRolePanel, ReportsPanel } from './StaffPortal.jsx'

const DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']

function MyTimetable({ timetable }) {
  if (!timetable.length) {
    return <p className="muted">No lessons yet — ask the admin to generate the timetable.</p>
  }
  const periods = [...new Set(timetable.map((l) => l.period))].sort((a, b) => a - b)
  const grid = {}
  for (const lesson of timetable) {
    grid[lesson.period] = grid[lesson.period] || {}
    grid[lesson.period][lesson.day] = lesson
  }
  const times = Object.fromEntries(timetable.map((l) => [l.period, `${l.start}–${l.end}`]))
  return (
    <table>
      <thead>
        <tr>
          <th>Period</th>
          {DAY_NAMES.map((d) => <th key={d}>{d}</th>)}
        </tr>
      </thead>
      <tbody>
        {periods.map((p) => (
          <tr key={p}>
            <td>
              P{p}
              <div className="muted">{times[p]}</div>
            </td>
            {[1, 2, 3, 4, 5].map((day) => {
              const lesson = grid[p]?.[day]
              return (
                <td key={day}>
                  {lesson && (
                    <>
                      {lesson.learning_area}
                      <div className="muted">
                        {gradeLabel(lesson.grade)}{lesson.stream}{lesson.room ? ` · ${lesson.room}` : ''}
                      </div>
                    </>
                  )}
                </td>
              )
            })}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function ScoreEntry({ assessments, onQueueChange }) {
  const [selectedId, setSelectedId] = useState('')
  const [rows, setRows] = useState([])
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  const assessment = assessments.find((a) => a.id === Number(selectedId))

  const load = useCallback(async () => {
    if (!assessment) return
    const params = `grade=${assessment.grade}` +
      (assessment.stream ? `&stream=${encodeURIComponent(assessment.stream)}` : '')
    const [learnersData, scoresData] = await Promise.all([
      apiGet(`/api/learners/?${params}`),
      apiGet(`/api/scores/?assessment=${assessment.id}`),
    ])
    const learners = learnersData.results || learnersData
    const scores = scoresData.results || scoresData
    const byLearner = Object.fromEntries(scores.map((s) => [s.learner, s]))
    setRows(
      learners.map((l) => ({
        learner: l.id,
        name: l.full_name,
        marks: byLearner[l.id] ? String(byLearner[l.id].marks) : '',
        level: byLearner[l.id]?.competency_level || null,
      })),
    )
    setMessage('')
  }, [assessment?.id])

  useEffect(() => {
    load()
  }, [load])

  async function save() {
    setBusy(true)
    const records = rows
      .filter((r) => r.marks !== '')
      .map((r) => ({ learner: r.learner, marks: Number(r.marks) }))
    const result = await apiWrite('/api/scores/bulk/', {
      assessment: assessment.id,
      records,
    })
    setBusy(false)
    onQueueChange()
    if (result.queued) {
      setMessage('Offline — marks queued locally, will sync when connection returns.')
      return
    }
    if (!result.ok) {
      setMessage('Rejected by server — check the marks.')
      return
    }
    const levels = Object.fromEntries(
      result.data.saved.map((s) => [s.learner, s.competency_level]),
    )
    setRows((prev) => prev.map((r) => ({ ...r, level: levels[r.learner] ?? r.level })))
    setMessage(
      `Saved ${result.data.saved.length} scores.` +
        (result.data.skipped.length ? ` Skipped: ${result.data.skipped.length} (blank/invalid).` : ''),
    )
  }

  return (
    <div className="card">
      <p>
        <select value={selectedId} onChange={(e) => setSelectedId(e.target.value)}>
          <option value="">Select assessment…</option>
          {assessments.map((a) => (
            <option key={a.id} value={a.id}>{a.label}</option>
          ))}
        </select>
      </p>
      {assessment && (
        <>
          <table>
            <thead>
              <tr><th>Learner</th><th>Marks (max {assessment.max_marks})</th><th>Level</th></tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={row.learner}>
                  <td>{row.name}</td>
                  <td>
                    <input
                      type="number"
                      min="0"
                      max={assessment.max_marks}
                      value={row.marks}
                      style={{ width: '6rem' }}
                      onChange={(e) =>
                        setRows((prev) =>
                          prev.map((r, j) => (j === i ? { ...r, marks: e.target.value } : r)),
                        )
                      }
                    />
                  </td>
                  <td>{row.level && <span className={`level ${row.level}`}>{row.level}</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p>
            <button className="primary" onClick={save} disabled={busy || !rows.length}>
              {busy ? 'Saving…' : 'Save marks'}
            </button>
          </p>
        </>
      )}
      {message && <p className="muted">{message}</p>}
    </div>
  )
}

export default function TeacherPortal({ onQueueChange }) {
  const [summary, setSummary] = useState(null)
  const [portal, setPortal] = useState(null)
  const [error, setError] = useState('')
  const [access, setAccess] = useState(null)
  const [tab, setTab] = useState('My Timetable')

  const load = useCallback(() => {
    apiGet('/api/teacher/summary/').then(setSummary).catch((e) => setError(e.message))
    apiGet('/api/my-portal/').then(setPortal).catch(() => setPortal(null))
    apiGet('/api/admissions/access/').then(setAccess).catch(() => setAccess(null))
  }, [])
  useEffect(load, [load])

  if (error) return <div className="error">{error}</div>
  if (!summary) return <p className="muted">Loading…</p>

  const pending = portal?.reports?.to_review?.length || 0
  const teamSize = portal?.team?.size || 0
  const tabs = [
    'My Role',
    ...(teamSize ? [`My Team (${teamSize})`] : []),
    'My Timetable', 'Score Entry', 'Attendance', 'Schemes of Work', 'Lesson Plans',
    'My Outcomes', 'Peer Review', 'Parents',
    ...(access?.can_admit ? ['Admissions'] : []),
    `Reports${pending ? ` (${pending})` : ''}`,
  ]

  return (
    <div>
      <p className="muted">
        {summary.teacher.name} (TSC {summary.teacher.tsc_number}) — {summary.teacher.school}
      </p>
      <nav className="tabs">
        {tabs.map((name) => {
          const key = name.split(' (')[0]
          return (
            <button key={key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>
              {name}
            </button>
          )
        })}
      </nav>

      {tab === 'My Role' && (
        portal ? <MyRolePanel data={portal} onRefresh={load} /> : <p className="muted">Loading…</p>
      )}
      {tab === 'My Team' && <MyTeam />}
      {tab === 'Admissions' && <Admission onAdmitted={load} />}
      {tab === 'My Outcomes' && (
        <>
          <TeacherDetail teacherId={summary.teacher.id} />
          <PdRecords />
        </>
      )}
      {tab === 'Peer Review' && <PeerReview />}
      {tab === 'Parents' && <StaffParentThreads />}
      {tab === 'Lesson Plans' && <LessonPlans summary={summary} />}
      {tab === 'Reports' && (
        portal ? <ReportsPanel data={portal} onRefresh={load} /> : <p className="muted">Loading…</p>
      )}

      {tab === 'My Timetable' && (
        <div className="card">
          <MyTimetable timetable={summary.timetable} />
        </div>
      )}

      {tab === 'Score Entry' && (
        <ScoreEntry assessments={summary.assessments} onQueueChange={onQueueChange} />
      )}

      {tab === 'Attendance' && <Attendance onQueueChange={onQueueChange} />}

      {tab === 'Schemes of Work' && (
        <>
          <TeacherSchemes summary={summary} onRefresh={load} />
          {summary.announcements.length > 0 && (
            <div className="card">
              <p className="muted">Announcements</p>
              {summary.announcements.map((a) => (
                <p key={a.id}>
                  <b>{a.title}</b> <span className="muted">({a.date})</span>
                  <br />
                  {a.body}{' '}
                  {a.meeting_link && (
                    <a href={a.meeting_link} target="_blank" rel="noreferrer">Join meeting</a>
                  )}
                </p>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
