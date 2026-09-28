/**
 * useTaskTracker — singleton composable for tracking background task progress.
 *
 * Receives `progress` / `task_progress` / `task_done` WebSocket events and
 * maintains a reactive map of active tasks.  The TaskProgressPanel reads
 * this map and renders progress bars.
 *
 * Usage (in a background task on the Python side):
 *
 *   async with track_progress(_("Import"), user=email, total=n) as p:  # grunt.progress
 *       p.advance(1)
 *
 * or one-off updates with `grunt.publish.show_progress(...)`. The frontend
 * picks up the WS events and shows the panel; `restore()` brings back the
 * tasks still running after a page reload.
 */

import { computed, ref } from 'vue'
import client from '@/core/api/client'
import i18n from '@/plugins/i18n'

const t = (key: string): string => i18n.global.t(key)

// ── Data model ───────────────────────────────────────────────────────────────

export interface TaskEntry {
  /** Stable key — derived from title (trimmed lowercase) or explicit task_id. */
  id: string
  title: string
  count: number
  total: number
  percent: number
  description?: string
  /** 'bytes' — count/total are sizes (shown as MB/GB). */
  unit?: 'bytes' | null
  /** DocType whose open list refreshes when the task is done. */
  doctype?: string | null
  /** 'active' while running, 'done' / 'error' after completion. */
  status: 'active' | 'done' | 'error'
  startedAt: number    // Date.now()
  updatedAt: number    // Date.now()
}

// ── Singleton module-level state ─────────────────────────────────────────────

const _tasks = ref<Map<string, TaskEntry>>(new Map())

// IDs scheduled for auto-removal so we don't pile up timers.
const _removalTimers = new Map<string, ReturnType<typeof setTimeout>>()

/** Derive a stable ID from an arbitrary title string. */
function _titleToId(title: string): string {
  return title.trim().toLowerCase().replace(/\s+/g, '-').slice(0, 64)
}

// ── Mutations ────────────────────────────────────────────────────────────────

/** Update or create a task entry from a `progress` / `task_progress` event. */
function update(data: {
  title?: string
  task_id?: string
  count?: number
  total?: number
  percent?: number
  description?: string
  unit?: 'bytes' | null
  /** Server start time, epoch seconds — keeps the ETA right after a reload. */
  started_at?: number
}) {
  const title = data.title ?? t('Task')
  const id = data.task_id ?? _titleToId(title)
  const count = data.count ?? 0
  const total = data.total ?? 100
  const percent = data.percent ?? (total > 0 ? Math.round((count / total) * 100) : 0)

  // Cancel any pending auto-removal for this task (it has new data).
  const existing_timer = _removalTimers.get(id)
  if (existing_timer) {
    clearTimeout(existing_timer)
    _removalTimers.delete(id)
  }

  const now = Date.now()
  const existing = _tasks.value.get(id)

  _tasks.value.set(id, {
    id,
    title,
    count,
    total,
    percent,
    description: data.description ?? existing?.description,
    unit: data.unit ?? existing?.unit,
    status: percent >= 100 ? 'done' : 'active',
    startedAt: data.started_at ? data.started_at * 1000 : (existing?.startedAt ?? now),
    updatedAt: now,
  })

  // Auto-remove completed tasks after 4 seconds.
  if (percent >= 100) {
    _scheduleRemoval(id, 4_000)
  }
}

/** Mark a task as done or errored (sent from the backend task_done event). */
function done(data: {
  task_id?: string
  title?: string
  status?: 'done' | 'error'
  message?: string
  doctype?: string | null
}) {
  const id = data.task_id ?? _titleToId(data.title ?? t('task'))
  const existing = _tasks.value.get(id)
  if (!existing) return

  _tasks.value.set(id, {
    ...existing,
    doctype: data.doctype ?? existing.doctype,
    status: data.status ?? 'done',
    percent: data.status === 'error' ? existing.percent : 100,
    description: data.message ?? existing.description,
    updatedAt: Date.now(),
  })

  _scheduleRemoval(id, data.status === 'error' ? 10_000 : 4_000)
}

/** Immediately remove a task (user dismissed it). */
function dismiss(id: string) {
  _tasks.value.delete(id)
  const t = _removalTimers.get(id)
  if (t) { clearTimeout(t); _removalTimers.delete(id) }
}

function _scheduleRemoval(id: string, delayMs: number) {
  const t = setTimeout(() => {
    _tasks.value.delete(id)
    _removalTimers.delete(id)
  }, delayMs)
  _removalTimers.set(id, t)
}

/** Pick up the tasks still running on the server (after a page reload). */
async function restore() {
  try {
    const { data } = await client.post('/api/v1/method/grunt.progress.active_tasks', {})
    for (const task of (data?.data ?? []) as Parameters<typeof update>[0][]) update(task)
  } catch {
    // not signed in / no Redis — nothing to restore
  }
}

// ── Public composable ─────────────────────────────────────────────────────────

export function useTaskTracker() {
  return {
    /** All task entries sorted: active first (by start time), then completed by updatedAt desc. */
    tasks: computed(() =>
      [..._tasks.value.values()].sort((a, b) => {
        if (a.status === 'active' && b.status !== 'active') return -1
        if (b.status === 'active' && a.status !== 'active') return 1
        if (a.status === 'active' && b.status === 'active') return a.startedAt - b.startedAt
        return b.updatedAt - a.updatedAt
      }),
    ),
    /** True when there is at least one active (non-done) task. */
    hasActive: computed(() =>
      [..._tasks.value.values()].some(t => t.status === 'active'),
    ),
    /** Total count of tracked tasks (including recently completed). */
    count: computed(() => _tasks.value.size),

    update,
    done,
    dismiss,
    restore,
  }
}
