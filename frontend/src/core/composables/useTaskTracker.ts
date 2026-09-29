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

const t = (key: string, params: Record<string, unknown> = {}): string => i18n.global.t(key, params)

// ── Data model ───────────────────────────────────────────────────────────────

export type TaskStatus = 'active' | 'done' | 'error' | 'cancelled'

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
  status: TaskStatus
  /** The task stops on request (the panel shows a cancel button while it runs). */
  cancellable?: boolean
  /** Cancel was requested, the task hasn't stopped yet. */
  cancelling?: boolean
  /** «Step N of M» when the task has distinct parts (0 = none). */
  step?: number
  steps?: number
  /** Seconds left at the pace of the last {@link ETA_WINDOW_MS} — unknown until it's measured. */
  etaSeconds?: number
  startedAt: number    // Date.now()
  updatedAt: number    // Date.now()
}

// ── Singleton module-level state ─────────────────────────────────────────────

const _tasks = ref<Map<string, TaskEntry>>(new Map())

/** Height of the open task panel (0 when hidden) — toasts stack above it. */
const _panelHeight = ref(0)

/**
 * ETA follows the recent pace, not the average since the start: a backup's
 * database part flies, its files crawl — the average would promise "< 1 min"
 * all through the slow part.
 */
const ETA_WINDOW_MS = 15_000
const ETA_MIN_SPAN_MS = 3_000
const _samples = new Map<string, { at: number; count: number }[]>()

function _eta(id: string, now: number, count: number, total: number): number | undefined {
  const samples = (_samples.get(id) ?? []).filter(s => s.at >= now - ETA_WINDOW_MS && s.count <= count)
  samples.push({ at: now, count })
  _samples.set(id, samples)
  const first = samples[0]!
  const span = now - first.at
  if (span < ETA_MIN_SPAN_MS || count <= first.count || total <= count) return undefined
  return ((total - count) * span) / (count - first.count) / 1000
}

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
  cancellable?: boolean
  step?: number
  steps?: number
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
    description: existing?.cancelling ? existing.description : (data.description ?? existing?.description),
    unit: data.unit ?? existing?.unit,
    cancellable: data.cancellable ?? existing?.cancellable,
    cancelling: existing?.cancelling,
    step: data.step ?? existing?.step,
    steps: data.steps ?? existing?.steps,
    etaSeconds: _eta(id, now, count, total),
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
  status?: Exclude<TaskStatus, 'active'>
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
    percent: data.status === 'error' || data.status === 'cancelled' ? existing.percent : 100,
    cancelling: false,
    description: data.status === 'cancelled' ? t('Cancelled') : (data.message ?? existing.description),
    updatedAt: Date.now(),
  })

  _scheduleRemoval(id, data.status === 'error' ? 10_000 : 4_000)
}

/** Ask the server to stop a running task; the panel shows «Cancelling…» until it does. */
async function cancel(id: string) {
  const task = _tasks.value.get(id)
  if (!task || task.status !== 'active') return
  _tasks.value.set(id, { ...task, cancelling: true, description: t('Cancelling…') })
  try {
    await client.post('/api/v1/method/grunt.progress.cancel_task', { task_id: id })
  } catch {
    _tasks.value.set(id, { ...task, cancelling: false })
  }
}

/** Immediately remove a task (user dismissed it). */
function dismiss(id: string) {
  _tasks.value.delete(id)
  _samples.delete(id)
  const t = _removalTimers.get(id)
  if (t) { clearTimeout(t); _removalTimers.delete(id) }
}

function _scheduleRemoval(id: string, delayMs: number) {
  const t = setTimeout(() => {
    _tasks.value.delete(id)
    _samples.delete(id)
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
    cancel,
    restore,
    panelHeight: _panelHeight,
  }
}
