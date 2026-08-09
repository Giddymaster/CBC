import { useCallback, useEffect, useState } from 'react'
import Admission from './Admission.jsx'
import { PdRecords, PeerReview, TeacherDetail } from './Analysis.jsx'
import { StaffParentThreads } from './ParentMessages.jsx'
import { apiGet, apiWrite } from './api.js'
import Attendance from './Attendance.jsx'
import Broadsheet from './Broadsheet.jsx'
import { gradeLabel, subjectColor } from './format.js'
import LessonPlans from './LessonPlans.jsx'
import TeacherSchemes from './Schemes.jsx'
import SchoolStructure from './SchoolStructure.jsx'
import MyTeam from './MyTeam.jsx'
import {
  ActionCard, ActionGrid, BackBar, BottomNav, PickList, PortalHero, Trail, count,
} from './portalUi.jsx'
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
          <th>Day</th>
          {periods.map((p) => (
            <th key={p}>P{p}<div className="muted">{times[p]}</div></th>
          ))}
        </tr>
      </thead>
      <tbody>
        {[1, 2, 3, 4, 5].map((day) => (
          <tr key={day}>
            <td><b>{DAY_NAMES[day - 1]}</b></td>
            {periods.map((p) => {
              const lesson = grid[p]?.[day]
              return (
                <td key={p}
                  style={lesson ? { background: subjectColor(lesson.learning_area) } : undefined}>
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

// Mirror of Assessment.level_for on the server, fed by the rubric the summary
// endpoint ships. Preview only — the stored level is derived again on save.
function levelFor(marks, assessment) {
  if (marks === '' || marks == null) return null
  const pct = assessment.max_marks ? (Number(marks) / assessment.max_marks) * 100 : 0
  for (const [bandMin, level] of assessment.rubric || []) {
    if (pct >= bandMin) return level
  }
  if (assessment.rubric?.length) return 'BE'
  if (pct >= 80) return 'EE'
  if (pct >= 60) return 'ME'
  if (pct >= 40) return 'AE'
  return 'BE'
}

// Slider takes the colour of the level the mark would earn.
const LEVEL_ACCENT = { EE: '#2f855a', ME: '#2b6cb0', AE: '#dd6b20', BE: '#c53030' }

function ScoreRow({ row, index, assessment, onMarks }) {
  const level = levelFor(row.marks, assessment)
  return (
    <div className="score-row">
      <div className="score-name">
        <span className="score-idx">{index}.</span>
        {row.name}
      </div>
      <div className="score-controls">
        <input
          type="range"
          min="0"
          max={assessment.max_marks}
          value={row.marks === '' ? 0 : row.marks}
          className={`score-slider${row.marks === '' ? ' unset' : ''}`}
          style={level ? { accentColor: LEVEL_ACCENT[level] } : undefined}
          aria-label={`Marks for ${row.name}`}
          onChange={(e) => onMarks(row.learner, e.target.value)}
        />
        <span className="score-marks">
          <input
            type="number"
            min="0"
            max={assessment.max_marks}
            value={row.marks}
            onChange={(e) => onMarks(row.learner, e.target.value)}
          />
          / {assessment.max_marks}
        </span>
        {level
          ? <span className={`level ${level}`}>{level}</span>
          : <span className="score-none">—</span>}
      </div>
    </div>
  )
}

const KIND_LABEL = {
  CAT1: 'CAT 1',
  CAT2: 'CAT 2',
  ENDTERM: 'End of Term Exam',
  FORMATIVE: 'Formative assessment',
}

function ScoreEntry({ classes, assessments, onQueueChange }) {
  // The drill: class → learning area → assessment. A teacher thinks in
  // classes first, so the picker does too.
  const [classKey, setClassKey] = useState('')
  const [areaName, setAreaName] = useState('')
  const [selectedId, setSelectedId] = useState('')
  const [rows, setRows] = useState([])
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [search, setSearch] = useState('')
  const [ungradedOnly, setUngradedOnly] = useState(false)

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
        marks: byLearner[l.id] ? String(Number(byLearner[l.id].marks)) : '',
      })),
    )
    setMessage('')
    setSearch('')
    setUngradedOnly(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- identity by id:
    // `assessments` is refetched wholesale, so a same-id object is same-data.
  }, [assessment?.id])

  useEffect(() => {
    load()
  }, [load])

  const setMarks = (learnerId, value) =>
    setRows((prev) =>
      prev.map((r) => (r.learner === learnerId ? { ...r, marks: value } : r)),
    )

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
    setMessage(
      `Saved ${result.data.saved.length} scores.` +
        (result.data.skipped.length ? ` Skipped: ${result.data.skipped.length} (blank/invalid).` : ''),
    )
  }

  const graded = rows.filter((r) => r.marks !== '').length
  const done = rows.length > 0 && graded === rows.length
  const needle = search.trim().toLowerCase()
  const shown = rows.filter(
    (r) =>
      (!needle || r.name.toLowerCase().includes(needle)) &&
      (!ungradedOnly || r.marks === ''),
  )

  // The class bar comes from the TIMETABLE — the classes this teacher is
  // assigned (all classes, for the head and deputy) — not from whichever
  // assessments happen to exist. classKey stays "grade|stream" underneath.
  const grades = [...new Set(classes.map((c) => c.grade))].sort((x, y) => x - y)
  const [pickedGrade, pickedStream] = classKey
    ? [Number(classKey.split('|')[0]), classKey.split('|')[1]]
    : [null, '']
  const streamsFor = (g) =>
    [...new Set(classes.filter((c) => c.grade === g).map((c) => c.stream || ''))]
      .sort()
  const setClass = (g, s) => {
    setClassKey(g === null ? '' : `${g}|${s}`)
    setAreaName('')
    setSelectedId('')
  }

  // An assessment matches the class when its stream is the class's stream or
  // blank (a stream-blank assessment covers the whole grade).
  const assessmentsFor = (g, s, area) =>
    assessments.filter(
      (a) => a.grade === g && a.learning_area === area
        && (!a.stream || a.stream === s),
    )
  const areas = [...new Set(
    classes
      .filter((c) => c.grade === pickedGrade && (c.stream || '') === pickedStream)
      .map((c) => c.learning_area),
  )].sort().map((name) => ({
    key: name,
    label: name,
    hint: count(assessmentsFor(pickedGrade, pickedStream, name).length, 'assessment'),
  }))
  const inArea = classKey && areaName
    ? assessmentsFor(pickedGrade, pickedStream, areaName)
    : []

  const crumbs = [
    'Areas',
    ...(areaName ? [areaName] : []),
    ...(assessment ? [KIND_LABEL[assessment.kind] || assessment.kind] : []),
  ]
  const backTo = (i) => {
    if (i < 1) setAreaName('')
    setSelectedId('')
  }

  if (classes.length === 0) {
    return (
      <div className="card">
        <p className="muted">
          You have no classes on the timetable yet — the head teacher assigns
          who teaches what under School (Grades) → Teaching assignments.
        </p>
      </div>
    )
  }

  return (
    <div className="card">
      <p style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
        <select
          value={pickedGrade ?? ''}
          onChange={(e) => {
            const g = e.target.value === '' ? null : Number(e.target.value)
            setClass(g, g === null ? '' : streamsFor(g)[0] ?? '')
          }}
        >
          <option value="">Grade…</option>
          {grades.map((g) => (
            <option key={g} value={g}>{gradeLabel(g)}</option>
          ))}
        </select>
        {pickedGrade !== null && streamsFor(pickedGrade).some((s) => s !== '') && (
          <select
            value={pickedStream}
            onChange={(e) => setClass(pickedGrade, e.target.value)}
          >
            {streamsFor(pickedGrade).map((s) => (
              <option key={s} value={s}>{s || 'Whole grade'}</option>
            ))}
          </select>
        )}
        {!classKey && <span className="muted">Pick the class you are marking.</span>}
      </p>
      {classKey && crumbs.length > 1 && <Trail crumbs={crumbs} onCrumb={backTo} />}
      {classKey && !areaName && (
        <PickList prompt="Choose the learning area." options={areas}
          onPick={setAreaName} />
      )}
      {classKey && areaName && !assessment && (
        inArea.length > 0 ? (
          <PickList
            prompt="Choose the assessment."
            options={inArea.map((a) => ({
              key: String(a.id),
              label: KIND_LABEL[a.kind] || a.kind,
              hint: `Term ${a.term} · ${a.year} · out of ${a.max_marks}`,
            }))}
            onPick={setSelectedId}
          />
        ) : (
          <p className="muted">
            No assessment exists yet for {areaName} in this class — the office
            creates assessments (CAT 1, End of Term…) under Assessments.
          </p>
        )
      )}
      {assessment && (
        <>
          <div className="score-head">
            <div>
              <b>{assessment.label}</b>
              <div className="muted">Out of {assessment.max_marks} marks</div>
            </div>
            <span className={`badge ${done ? 'online' : 'queued'}`}>
              {done ? 'All graded' : 'In progress'}
            </span>
          </div>

          <div className="score-tools">
            <input
              className="score-search"
              placeholder="Search learners…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <button
              type="button"
              className={`grade-chip${ungradedOnly ? ' on' : ''}`}
              onClick={() => setUngradedOnly((v) => !v)}
            >
              Ungraded only
            </button>
          </div>
          <p className="muted score-progress">
            {graded}/{rows.length} graded
            {shown.length !== rows.length && ` · showing ${shown.length} of ${rows.length}`}
          </p>

          <div className="score-list">
            {shown.map((row) => (
              <ScoreRow
                key={row.learner}
                row={row}
                index={rows.findIndex((r) => r.learner === row.learner) + 1}
                assessment={assessment}
                onMarks={setMarks}
              />
            ))}
            {shown.length === 0 && (
              <p className="muted">
                {ungradedOnly ? 'Everyone shown is graded.' : 'No learners match.'}
              </p>
            )}
          </div>

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

// The dashboard's action cards: where each tab lives, in the language of what a
// teacher comes here to do. `when` hides cards the account has no use for.
const TEACHER_ACTIONS = [
  { tab: 'My Timetable', icon: 'calendar', tone: 'blue', title: 'My Timetable',
    desc: 'Your week — lessons, periods and rooms.', cta: 'Open timetable' },
  { tab: 'Score Entry', icon: 'pencil', tone: 'green', title: 'Score Entry',
    desc: 'Record marks; competency levels are worked out for you.', cta: 'Enter scores' },
  { tab: 'Attendance', icon: 'check', tone: 'teal', title: 'Attendance',
    desc: 'Mark the daily register for your class.', cta: 'Take attendance' },
  { tab: 'Schemes of Work', icon: 'book', tone: 'purple', title: 'Schemes of Work',
    desc: 'Plan the term and track curriculum coverage.', cta: 'Open schemes' },
  { tab: 'Lesson Plans', icon: 'clipboard', tone: 'orange', title: 'Lesson Plans',
    desc: 'Prepare lessons from your schemes of work.', cta: 'Plan lessons' },
  { tab: 'My Outcomes', icon: 'chart', tone: 'red', title: 'My Outcomes',
    desc: 'How your learners are performing, area by area.', cta: 'View outcomes' },
  { tab: 'Parents', icon: 'chat', tone: 'green', title: 'Parents',
    desc: 'Message the parents of your learners.', cta: 'Open messages' },
  { tab: 'Reports', icon: 'file', tone: 'orange', title: 'Reports',
    desc: 'Weekly staff reports — yours, and any waiting on you.',
    cta: 'Open reports', badge: (ctx) => ctx.pending },
  { tab: 'My Role', icon: 'user', tone: 'blue', title: 'My Role',
    desc: 'Your duties, tasks and messages from your supervisor.', cta: 'View role' },
  { tab: 'My Team', icon: 'users', tone: 'teal', title: 'My Team',
    desc: 'The staff who report to you.', cta: 'Open team',
    when: (ctx) => ctx.teamSize > 0, badge: (ctx) => ctx.teamSize },
  { tab: 'School (Grades)', icon: 'grid', tone: 'blue', title: 'School (Grades)',
    desc: 'Classes, streams, learning areas and teaching assignments.',
    cta: 'Open school', when: (ctx) => ctx.rankLevel >= 4 },
  { tab: 'Report Cards', icon: 'file', tone: 'red', title: 'Report Cards',
    desc: 'Class broadsheets, Excel exports and printable report forms.',
    cta: 'Open broadsheets', when: (ctx) => ctx.rankLevel >= 4 },
  { tab: 'Peer Review', icon: 'star', tone: 'purple', title: 'Peer Review',
    desc: 'Observe colleagues and read feedback on your teaching.', cta: 'Open reviews' },
  { tab: 'Admissions', icon: 'plus', tone: 'green', title: 'Admissions',
    desc: 'Admit a learner into the school.', cta: 'Admit a learner',
    when: (ctx) => ctx.canAdmit },
]

const TEACHER_NAV = [
  { key: 'Dashboard', label: 'Dashboard', icon: 'grid' },
  { key: 'My Timetable', label: 'Timetable', icon: 'calendar' },
  { key: 'Score Entry', label: 'Scores', icon: 'pencil' },
  { key: 'Attendance', label: 'Attendance', icon: 'check' },
  { key: 'Parents', label: 'Parents', icon: 'chat' },
]

// Monday=1 … Friday=5, matching lesson.day in the timetable.
function todayLessons(timetable) {
  const day = new Date().getDay()
  return timetable.filter((l) => l.day === day).length
}

export default function TeacherPortal({ onQueueChange }) {
  const [summary, setSummary] = useState(null)
  const [portal, setPortal] = useState(null)
  const [error, setError] = useState('')
  const [access, setAccess] = useState(null)
  const [tab, setTab] = useState('Dashboard')

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
  const ctx = {
    pending,
    teamSize,
    canAdmit: Boolean(access?.can_admit),
    // Head teacher / deputy — they run the school day, so they also see the
    // school structure and set teaching assignments.
    rankLevel: portal?.team?.rank_level || 0,
  }
  const actions = TEACHER_ACTIONS.filter((a) => !a.when || a.when(ctx))

  const lessonsToday = todayLessons(summary.timetable)
  const openTab = (name) => { setTab(name); window.scrollTo(0, 0) }

  return (
    <div className="portal-shell">
      {tab !== 'Dashboard' && (
        <BackBar
          title={actions.find((a) => a.tab === tab)?.title || tab}
          onBack={() => openTab('Dashboard')}
        />
      )}

      {tab === 'Dashboard' && (
        <>
          <PortalHero
            icon="user"
            title={summary.teacher.name}
            subtitle={`TSC ${summary.teacher.tsc_number} · ${summary.teacher.school}`}
            chips={[
              `${lessonsToday} lesson${lessonsToday === 1 ? '' : 's'} today`,
              ...(pending ? [`${pending} report${pending === 1 ? '' : 's'} to review`] : []),
              ...(teamSize ? [`Team of ${teamSize}`] : []),
            ]}
          />
          <ActionGrid>
            {actions.map((a) => (
              <ActionCard
                key={a.tab}
                icon={a.icon}
                tone={a.tone}
                title={a.title}
                desc={a.desc}
                cta={a.cta}
                badge={a.badge ? a.badge(ctx) : 0}
                onOpen={() => openTab(a.tab)}
              />
            ))}
          </ActionGrid>
        </>
      )}

      {tab === 'My Role' && (
        portal ? <MyRolePanel data={portal} onRefresh={load} /> : <p className="muted">Loading…</p>
      )}
      {tab === 'My Team' && <MyTeam />}
      {tab === 'School (Grades)' && <SchoolStructure grade={null} />}
      {tab === 'Report Cards' && <Broadsheet grade={null} />}
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
        <ScoreEntry
          classes={summary.teaching_classes || []}
          assessments={summary.assessments}
          onQueueChange={onQueueChange}
        />
      )}

      {/* Head and deputy see the marked register like the office does —
          marking belongs to the class teachers. */}
      {tab === 'Attendance' && (
        <Attendance onQueueChange={onQueueChange} canMark={ctx.rankLevel < 4} />
      )}

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

      <BottomNav items={TEACHER_NAV} active={tab} onSelect={openTab} />
    </div>
  )
}
