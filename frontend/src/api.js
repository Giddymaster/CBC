// API client with offline tolerance.
//
// Reads: plain fetch, fail fast.
// Writes: apiWrite() attaches a client-generated Idempotency-Key. If the
// network is down, the request is queued in localStorage and replayed when
// connectivity returns — the backend's idempotency store makes replays safe
// even if the original request actually landed.

const QUEUE_KEY = 'cbc-offline-queue'
const TOKEN_KEY = 'cbc-token'

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

function headers(extra = {}) {
  const token = getToken()
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Token ${token}` } : {}),
    ...extra,
  }
}

// A dead or revoked token should send the user back to the login screen rather
// than leaving every panel stuck on an unexplained error.
let onUnauthorized = null
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn
}

function checkAuth(res) {
  if (res.status === 401 && onUnauthorized) {
    clearToken()
    onUnauthorized()
  }
  return res
}

export async function apiGet(path) {
  const res = checkAuth(await fetch(path, { headers: headers() }))
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`)
  return res.json()
}

// Multipart upload (files can't be queued offline — fail fast instead).
export async function apiUpload(path, formData, { method = 'POST' } = {}) {
  const token = getToken()
  const res = checkAuth(
    await fetch(path, {
      method,
      headers: token ? { Authorization: `Token ${token}` } : {},
      body: formData,
    }),
  )
  return { ok: res.ok, data: await res.json().catch(() => null) }
}

function loadQueue() {
  try {
    return JSON.parse(localStorage.getItem(QUEUE_KEY)) || []
  } catch {
    return []
  }
}

function saveQueue(queue) {
  localStorage.setItem(QUEUE_KEY, JSON.stringify(queue))
}

export function queuedCount() {
  return loadQueue().length
}

export async function apiWrite(path, body, { method = 'POST' } = {}) {
  const idempotencyKey = crypto.randomUUID()
  const entry = { path, body, method, idempotencyKey, queuedAt: Date.now() }
  try {
    const res = checkAuth(
      await fetch(path, {
        method,
        headers: headers({ 'Idempotency-Key': idempotencyKey }),
        body: JSON.stringify(body),
      }),
    )
    if (res.status >= 500) throw new Error(`server ${res.status}`)
    return { ok: res.ok, queued: false, data: await res.json().catch(() => null) }
  } catch {
    // Network down or server unreachable: queue for replay.
    saveQueue([...loadQueue(), entry])
    return { ok: false, queued: true, data: null }
  }
}

// Writes the server refused outright (4xx). Retrying can never fix these, so
// they leave the queue — but they must not vanish silently: a teacher whose
// register was rejected needs to know it never landed.
const REJECTED_KEY = 'cbc-rejected-writes'

export function rejectedWrites() {
  try {
    return JSON.parse(localStorage.getItem(REJECTED_KEY)) || []
  } catch {
    return []
  }
}

export function clearRejectedWrites() {
  localStorage.removeItem(REJECTED_KEY)
}

export async function flushQueue() {
  const queue = loadQueue()
  if (!queue.length) return { flushed: 0, rejected: 0 }
  const remaining = []
  const rejected = []
  let flushed = 0
  for (const entry of queue) {
    try {
      const res = checkAuth(
        await fetch(entry.path, {
          method: entry.method,
          headers: headers({ 'Idempotency-Key': entry.idempotencyKey }),
          body: JSON.stringify(entry.body),
        }),
      )
      if (res.status >= 500) throw new Error('retry later')
      if (res.ok) {
        flushed += 1
      } else {
        const detail = await res.json().catch(() => null)
        rejected.push({ ...entry, status: res.status, detail })
      }
    } catch {
      remaining.push(entry)
    }
  }
  saveQueue(remaining)
  if (rejected.length) {
    localStorage.setItem(REJECTED_KEY, JSON.stringify([...rejectedWrites(), ...rejected]))
  }
  return { flushed, rejected: rejected.length }
}

// Replay whenever connectivity returns, plus a slow safety interval.
export function startQueueFlusher(onFlush) {
  const flush = async () => {
    const { flushed, rejected } = await flushQueue()
    if ((flushed > 0 || rejected > 0) && onFlush) onFlush(flushed, rejected)
  }
  window.addEventListener('online', flush)
  const interval = setInterval(flush, 30_000)
  return () => {
    window.removeEventListener('online', flush)
    clearInterval(interval)
  }
}
