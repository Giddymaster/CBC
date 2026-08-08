// Grade labels: PP1/PP2 are stored as -1/0, everything else is G1..G12.
export function gradeLabel(grade) {
  const g = Number(grade)
  if (g === -2) return 'PG'
  if (g === -1) return 'PP1'
  if (g === 0) return 'PP2'
  return `G${g}`
}

// Every grade in the school, in order: PG, PP1, PP2, G1..G12.
export const ALL_GRADES = [-2, -1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]

// Today's date in the user's own timezone (toISOString() is UTC and lands on
// the wrong day in Kenya (UTC+3) during the early hours).
export function todayLocal() {
  const d = new Date()
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10)
}

// `?grade=5` style query suffix, or '' when no grade is selected.
export function gradeParam(grade, key = 'grade') {
  return grade === null || grade === undefined ? '' : `${key}=${grade}`
}

// A stable light background per learning area, so a timetable reads by colour
// the way a wall chart does. Same name → same hue, on every grid.
export function subjectColor(name) {
  if (!name) return undefined
  let hash = 0
  for (let i = 0; i < name.length; i += 1) {
    hash = (hash * 31 + name.charCodeAt(i)) >>> 0
  }
  return `hsl(${hash % 360}, 60%, 88%)`
}
