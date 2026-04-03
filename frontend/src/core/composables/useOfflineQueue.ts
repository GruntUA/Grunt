/**
 * useOfflineQueue — IndexedDB-backed mutation queue for offline support.
 *
 * When the browser is offline, POST/PUT/PATCH/DELETE requests that fail with a
 * network error are enqueued here.  When the connection is restored,
 * `offlineQueue.flush()` replays them in order and removes successful ones.
 *
 * DB: grunt_offline v1
 * Store: mutations  { id (auto), method, url, data, headers, timestamp }
 */

import { ref } from 'vue'

const DB_NAME = 'grunt_offline'
const DB_VERSION = 1
const STORE = 'mutations'

export interface QueuedMutation {
  id?: number
  method: string     // 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  url: string
  data: unknown
  headers: Record<string, string>
  timestamp: number
}

// Reactive count — updated whenever queue changes
export const pendingCount = ref(0)

// ── IndexedDB helpers ──────────────────────────────────────────────────────

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = (e) => {
      const db = (e.target as IDBOpenDBRequest).result
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: 'id', autoIncrement: true })
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

async function idbGetAll(): Promise<QueuedMutation[]> {
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readonly')
    const req = tx.objectStore(STORE).getAll()
    req.onsuccess = () => resolve(req.result as QueuedMutation[])
    req.onerror = () => reject(req.error)
  })
}

async function idbAdd(item: Omit<QueuedMutation, 'id'>): Promise<number> {
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite')
    const req = tx.objectStore(STORE).add(item)
    req.onsuccess = () => resolve(req.result as number)
    req.onerror = () => reject(req.error)
  })
}

async function idbDelete(id: number): Promise<void> {
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite')
    const req = tx.objectStore(STORE).delete(id)
    req.onsuccess = () => resolve()
    req.onerror = () => reject(req.error)
  })
}

async function syncCount() {
  const items = await idbGetAll()
  pendingCount.value = items.length
}

// ── Public API ─────────────────────────────────────────────────────────────

const REPLAYABLE = new Set(['post', 'put', 'patch', 'delete'])

async function enqueue(mutation: Omit<QueuedMutation, 'id' | 'timestamp'>): Promise<void> {
  if (!REPLAYABLE.has(mutation.method.toLowerCase())) return
  await idbAdd({ ...mutation, timestamp: Date.now() })
  await syncCount()
}

/**
 * Replay all queued mutations in order.
 * Returns the number of successfully synced items.
 */
async function flush(): Promise<number> {
  const items = await idbGetAll()
  if (!items.length) return 0

  // Dynamic import to avoid circular dependency with client.ts
  const { default: client } = await import('@/core/api/client')
  let synced = 0

  for (const item of items) {
    try {
      await client.request({
        method: item.method,
        url: item.url,
        data: item.data,
        headers: { ...item.headers, 'X-Offline-Replay': '1' },
      })
      await idbDelete(item.id!)
      synced++
    } catch {
      // Leave failed items in the queue — they'll be retried next time
    }
  }

  await syncCount()
  return synced
}

// Initialize count on module load
syncCount().catch(() => { /* IDB may not be available in SSR/test */ })

export const offlineQueue = { enqueue, flush, syncCount }
