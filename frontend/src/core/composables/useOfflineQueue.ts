/**
 * Offline change queue — document create / update / delete made without a
 * connection are kept in IndexedDB and sent when it returns.
 *
 * Safe by construction:
 *  - only document CRUD (`/api/v1/docs/...`) is queued; actions and other RPCs
 *    (send, sign, workflow…) fail instead of running later on stale state;
 *  - no credentials are stored — a replay uses whatever session is current,
 *    and only replays the changes of the user who made them;
 *  - an update carries the `modified_at` it was based on
 *    (`__base_modified_at`): if someone changed the document meanwhile the
 *    server answers 409 and the change becomes a *conflict*, never overwriting;
 *  - a create carries an `Idempotency-Key`, so a retry can't duplicate it;
 *  - a refused change (4xx) stops retrying and waits for the user
 *    (retry / discard) instead of looping forever.
 */

import { computed, ref } from 'vue'

const DB_NAME = 'grunt_offline'
const DB_VERSION = 2 // v1 stored bearer tokens — its store is dropped on upgrade
const STORE = 'changes'

export type ChangeStatus = 'pending' | 'conflict' | 'failed'

export interface QueuedChange {
  id?: number
  method: 'post' | 'put' | 'patch' | 'delete'
  url: string
  data?: Record<string, unknown>
  doctype: string
  docId: string | null
  user: string
  status: ChangeStatus
  error?: string
  idempotencyKey?: string
  timestamp: number
}

/** Thrown to the caller instead of a response when a change was queued. */
export class OfflineQueuedError extends Error {
  constructor() {
    super("Немає з'єднання — зміни збережено на пристрої й буде надіслано автоматично")
    this.name = 'OfflineQueuedError'
  }
}

export function isOfflineQueued(error: unknown): error is OfflineQueuedError {
  return error instanceof OfflineQueuedError
}

/** The current user's queued changes (all statuses), oldest first. */
export const queue = ref<QueuedChange[]>([])
export const pendingCount = computed(() => queue.value.length)

const DOC_URL = /^(?:https?:\/\/[^/]+)?\/api\/v1\/docs\/([^/?]+)(?:\/([^/?]+))?\/?(?:\?|$)/

/** Document CRUD only: POST on a list URL, PUT/PATCH/DELETE on a document URL. */
export function parseDocUrl(method: string, url: string): { doctype: string; docId: string | null } | null {
  const m = DOC_URL.exec(url)
  if (!m) return null
  const [, doctype, docId] = m
  const verb = method.toLowerCase()
  if (verb === 'post' && !docId) return { doctype: decodeURIComponent(doctype), docId: null }
  if ((verb === 'put' || verb === 'patch' || verb === 'delete') && docId) {
    return { doctype: decodeURIComponent(doctype), docId: decodeURIComponent(docId) }
  }
  return null
}

// ── IndexedDB ──────────────────────────────────────────────────────────────

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = () => {
      const db = req.result
      if (db.objectStoreNames.contains('mutations')) db.deleteObjectStore('mutations')
      if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE, { keyPath: 'id', autoIncrement: true })
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

async function tx<T>(mode: IDBTransactionMode, run: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const req = run(db.transaction(STORE, mode).objectStore(STORE))
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

async function currentUser(): Promise<string> {
  const { useAuthStore } = await import('@/stores/auth')
  return useAuthStore().user?.email ?? ''
}

/** Reload the reactive list (current user's changes) from IndexedDB. */
export async function refreshQueue(): Promise<void> {
  const user = await currentUser()
  const all = await tx<QueuedChange[]>('readonly', (s) => s.getAll())
  queue.value = all.filter((c) => c.user === user).sort((a, b) => a.timestamp - b.timestamp)
}

async function put(change: QueuedChange): Promise<void> {
  // Items read from `queue` are Vue proxies — IndexedDB can't structured-clone those.
  const plain = JSON.parse(JSON.stringify(change)) as QueuedChange
  await tx('readwrite', (s) => s.put(plain))
}

// ── Public API ─────────────────────────────────────────────────────────────

/** Queue a document change that failed for lack of a connection. */
export async function enqueue(method: string, url: string, data: unknown): Promise<boolean> {
  const target = parseDocUrl(method, url)
  if (!target) return false
  const payload = data && typeof data === 'object' ? { ...(data as Record<string, unknown>) } : undefined
  const verb = method.toLowerCase() as QueuedChange['method']
  if (payload && (verb === 'put' || verb === 'patch') && payload.modified_at && !payload.__base_modified_at) {
    payload.__base_modified_at = payload.modified_at
  }
  const user = await currentUser()
  await tx('readwrite', (s) =>
    s.add({
      method: verb,
      url,
      data: payload,
      ...target,
      user,
      status: 'pending',
      idempotencyKey: verb === 'post' ? crypto.randomUUID() : undefined,
      timestamp: Date.now(),
    } satisfies QueuedChange),
  )
  await refreshQueue()
  return true
}

function errorMessage(err: any): string {
  const body = err?.response?.data
  return body?.error?.message ?? body?.detail ?? err?.message ?? 'Помилка'
}

/**
 * Send the current user's pending changes in order. Stops at the first
 * network failure (still offline). Returns how many were accepted.
 */
export async function flush(): Promise<number> {
  await refreshQueue()
  const { default: client } = await import('@/core/api/client')
  let synced = 0
  for (const change of queue.value.filter((c) => c.status === 'pending')) {
    try {
      await client.request({
        method: change.method,
        url: change.url,
        data: change.data,
        headers: {
          'X-Offline-Replay': '1',
          ...(change.idempotencyKey ? { 'Idempotency-Key': change.idempotencyKey } : {}),
        },
      })
      await tx('readwrite', (s) => s.delete(change.id!))
      synced++
    } catch (err: any) {
      const status = err?.response?.status as number | undefined
      if (!status || status >= 500) break // offline again / server trouble — try later
      await put({ ...change, status: status === 409 ? 'conflict' : 'failed', error: errorMessage(err) })
    }
  }
  await refreshQueue()
  if (synced) window.dispatchEvent(new CustomEvent('grunt:offline-synced', { detail: synced }))
  return synced
}

export async function retry(id: number): Promise<number> {
  const change = queue.value.find((c) => c.id === id)
  if (!change) return 0
  const data = { ...change.data }
  // Retrying a conflict means "apply mine anyway" — drop the stale base.
  if (change.status === 'conflict') delete data.__base_modified_at
  await put({ ...change, data, status: 'pending', error: undefined })
  return flush()
}

export async function discard(id: number): Promise<void> {
  await tx('readwrite', (s) => s.delete(id))
  await refreshQueue()
}

export const offlineQueue = { enqueue, flush, retry, discard, refreshQueue }
