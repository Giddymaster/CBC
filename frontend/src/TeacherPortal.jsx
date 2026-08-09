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
  ActionCard, ActionGrid, BackBar, BottomNav, PortalHero,
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
  RAT: 'RAT',
  MIDTERM: 'Midterm Exam',
  ENDTERM: 'Final Exam',
  FORMATIVE: 'Formative',
}
const KIND_ORDER = ['CAT1', 'CAT2', 'RAT', 'MIDTERM', 'ENDTERM', 'FORMATIVE']

function currentTerm() {
  const m = new Date().getMonth() + 1
  return m <= 4 ? 1 : m <= 8 ? 2 : 3
}

/** Every learner, not just the first page. */
async function fetchAllLearners(query) {
  const rows = []
  let url = `/api/learners/?page_size=500${query ? `&${query}` : ''}`
  while (url) {
    const d = await apiGet(url)
    rows.push(...(d.results || d))
    url = d.next ? d.next.slice(d.next.indexOf('/api/')) : null
  }
  return rows
}

/** Marks entry as the sheet a staff room knows: pick the class and subject,
 * and the whole class appears — ADM, name, one column per assessment — every
 * cell waiting to be filled. Columns come and go with "+ Add assessment". */
function ScoreEntry({ classes, assessments, onQueueChange, onRefresh }) {
  const [classKey, setClassKey] = useState('')
  const [areaName, setAreaName] = useState('')
  const [term, setTerm] = useState(currentTerm())
  const [year, setYear] = useState(new Date().getFullYear())
  const [learners, setLearners] = useState([])
  const [marks, setMarks] = useState({})   // `${assessmentId}|${learnerId}` -> string
  const [orig, setOrig] = useState({})
  const [search, setSearch] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [adding, setAdding] = useState(false)
  const [newKind, setNewKind] = useState('CAT1')
  const [newMax, setNewMax] = useState(30)

  // The class bar comes from the TIMETABLE — the classes this teacher is
  // assigned (all classes, for the head and deputy).
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
    setMessage('')
  }
  const areaNames = [...new Set(
    classes
      .filter((c) => c.grade === pickedGrade && (c.stream || '') === pickedStream)
      .map((c) => c.learning_area),
  )].sort()
  const areaId = classes.find(
    (c) => c.grade === pickedGrade && (c.stream || '') === pickedStream
      && c.learning_area === areaName,
  )?.learning_area_id

  // The sheet's columns: this class-subject's assessments for the term.
  const cols = assessments
    .filter((a) =>
      a.grade === pickedGrade && a.learning_area === areaName
      && (!a.stream || a.stream === pickedStream)
      && a.term === term && a.year === year)
    .sort((a, b) => KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind))
  const usedKinds = new Set(cols.map((a) => a.kind))

  // Rows: the class list.
  useEffect(() => {
    if (!classKey) { setLearners([]); return }
    const q = `grade=${pickedGrade}`
      + (pickedStream ? `&stream=${encodeURIComponent(pickedStream)}` : '')
    fetchAllLearners(q).then(setLearners).catch(() => setLearners([]))
    // eslint-disable-next-line react-hooks/exhaustive-deps -- keyed by class
  }, [classKey])

  // Cell values: whatever is already recorded, per column.
  const colIds = cols.map((a) => a.id).join(',')
  useEffect(() => {
    if (!colIds) { setMarks({}); setOrig({}); return }
    Promise.all(cols.map((a) =>
      apiGet(`/api/scores/?assessment=${a.id}&page_size=500`)
        .then((d) => (d.results || d).map((s) => [`${a.id}|${s.learner}`, String(Number(s.marks))]))
        .catch(() => []),
    )).then((chunks) => {
      const loaded = Object.fromEntries(chunks.flat())
      setMarks(loaded)
      setOrig(loaded)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps -- keyed by columns
  }, [colIds])

  async function save() {
    setBusy(true)
    let saved = 0
    let queued = false
    for (const a of cols) {
      const records = learners
        .filter((l) => {
          const key = `${a.id}|${l.id}`
          return (marks[key] ?? '') !== '' && marks[key] !== orig[key]
        })
        .map((l) => ({ learner: l.id, marks: Number(marks[`${a.id}|${l.id}`]) }))
      if (!records.length) continue
      const res = await apiWrite('/api/scores/bulk/', { assessment: a.id, records })
      if (res.queued) queued = true
      else if (res.ok) saved += res.data.saved.length
    }
    setBusy(false)
    setOrig({ ...marks })
    setMessage(
      queued
        ? 'Offline — marks queued locally, will sync when connection returns.'
        : saved
          ? `Saved ${saved} mark${saved === 1 ? '' : 's'}.`
          : 'Nothing new to save.',
    )
    onQueueChange?.()
  }

  async function addAssessment() {
    if (!areaId) return
    const res = await apiWrite('/api/assessments/', {
      kind: newKind,
      learning_area: areaId,
      grade: pickedGrade,
      stream: pickedStream,
      term,
      year,
      max_marks: Number(newMax) || 30,
    })
    if (res.ok) {
      setAdding(false)
      setMessage(`${KIND_LABEL[newKind] || newKind} added.`)
      onRefresh?.()
    } else {
      setMessage(res.data ? JSON.stringify(res.data) : 'Could not add the assessment.')
    }
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

  const needle = search.trim().toLowerCase()
  const shownLearners = learners.filter(
    (l) => !needle || l.full_name.toLowerCase().includes(needle),
  )

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
        {classKey && (
          <select value={areaName} onChange={(e) => { setAreaName(e.target.value); setMessage('') }}>
            <option value="">Learning area…</option>
            {areaNames.map((name) => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>
        )}
        {areaName && (
          <>
            <select value={term} onChange={(e) => setTerm(Number(e.target.value))}>
              {[1, 2, 3].map((t) => <option key={t} value={t}>Term {t}</option>)}
            </select>
            <input type="number" value={year} style={{ width: '5.5rem' }}
              onChange={(e) => setYear(Number(e.target.value))} />
          </>
        )}
        {!classKey && <span className="muted">Pick the class you are marking.</span>}
      </p>

      {classKey && areaName && (
        <>
          <p style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
            <input placeholder="Search learners…" value={search}
              onChange={(e) => setSearch(e.target.value)} style={{ padding: '0.35rem' }} />
            {!adding ? (
              <button type="button" className="grade-chip"
                onClick={() => {
                  // The select must start on a kind that is actually free —
                  // defaulting to CAT 1 when CAT 1 exists posts a duplicate.
                  const free = KIND_ORDER.filter((k) => !usedKinds.has(k))
                  setNewKind(free[0] || '')
                  setAdding(true)
                }}>
                + Add assessment
              </button>
            ) : (
              <span style={{ display: 'inline-flex', gap: '0.4rem', alignItems: 'center',
                             border: '1px dashed #cbd5e0', borderRadius: '6px',
                             padding: '0.3rem 0.5rem' }}>
                {newKind ? (
                  <>
                    <select value={newKind} onChange={(e) => setNewKind(e.target.value)}>
                      {KIND_ORDER.filter((k) => !usedKinds.has(k)).map((k) => (
                        <option key={k} value={k}>{KIND_LABEL[k]}</option>
                      ))}
                    </select>
                    <label className="muted">
                      Out of{' '}
                      <input type="number" min="1" value={newMax} style={{ width: '4rem' }}
                        onChange={(e) => setNewMax(e.target.value)} />
                    </label>
                    <button type="button" className="primary" onClick={addAssessment}>Add</button>
                  </>
                ) : (
                  <span className="muted">
                    Every assessment kind already exists for this term.
                  </span>
                )}
                <button type="button" onClick={() => setAdding(false)}>×</button>
              </span>
            )}
            <span className="muted">
              {learners.length} learners · Term {term} {year}
            </span>
          </p>

          {cols.length === 0 ? (
            <p className="muted">
              No assessments yet for {areaName} this term — add one above
              (CAT 1, Midterm, Final Exam…) and the marks columns appear here.
            </p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Adm No</th>
                  <th>Student Name</th>
                  {cols.map((a) => (
                    <th key={a.id}>
                      {KIND_LABEL[a.kind] || a.kind}
                      <div className="muted">/ {a.max_marks}</div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {shownLearners.map((l) => (
                  <tr key={l.id}>
                    <td className="muted">{l.admission_number}</td>
                    <td style={{ whiteSpace: 'nowrap' }}>{l.full_name}</td>
                    {cols.map((a) => {
                      const key = `${a.id}|${l.id}`
                      const dirty = (marks[key] ?? '') !== (orig[key] ?? '')
                      return (
                        <td key={a.id}>
                          <input
                            type="number"
                            min="0"
                            max={a.max_marks}
                            value={marks[key] ?? ''}
                            className={dirty ? 'mark-cell dirty' : 'mark-cell'}
                            onChange={(e) =>
                              setMarks((prev) => ({ ...prev, [key]: e.target.value }))
                            }
                          />
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {cols.length > 0 && (
            <p>
              <button className="primary" onClick={save} disabled={busy || !learners.length}>
                {busy ? 'Saving…' : 'Save marks'}
              </button>
              {message && <span className="muted"> {message}</span>}
            </p>
          )}
          {cols.length === 0 && message && <p className="muted">{message}</p>}
        </>
      )}
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
          onRefresh={load}
        />
      )}

      {/* Only the class teacher of a class marks its register; everyone
          else — head, deputy, subject teachers — reads the month record. */}
      {tab === 'Attendance' && (
        <Attendance
          onQueueChange={onQueueChange}
          classTeacherOf={summary.class_teacher_of || []}
        />
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
