// "Recently viewed documents" - on the server with the user's list settings
// (UserViewSettings, ref_doctype "*", view "recent"), so they are the same on
// every device; localStorage is the cache the pages read synchronously.
//
// A single source of truth for the shape and the storage key so the writer
// (AppFormView) and the reader (DeskPage) cannot drift apart.

import { ANY_DOCTYPE, viewSettingsApi } from '@/core/api/viewSettings'

const KEY = 'grunt_recent_docs'
const MAX = 20
const CHANGED_EVENT = 'grunt_recent_docs_changed'
const VIEW = 'recent'
const SAVE_DELAY_MS = 2000

export interface RecentDoc {
  workspace: string
  doctype: string
  id: string
  /** Resolved display title (title_field value), or the id when none exists. */
  title: string
  ts: number
}

function read(): RecentDoc[] {
  try {
    const saved = localStorage.getItem(KEY)
    return saved ? (JSON.parse(saved) as RecentDoc[]) : []
  } catch {
    return []
  }
}

function write(entries: RecentDoc[], { toServer = true } = {}): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(entries.slice(0, MAX)))
    window.dispatchEvent(new Event(CHANGED_EVENT))
  } catch {
    // ignore quota / serialization errors - history is best-effort
  }
  if (toServer) scheduleSave()
}

let _timer: ReturnType<typeof setTimeout> | null = null

// Opening documents one after another sends one request, not one per document.
function scheduleSave(): void {
  if (_timer) clearTimeout(_timer)
  _timer = setTimeout(() => {
    _timer = null
    void viewSettingsApi.save(ANY_DOCTYPE, VIEW, read()).catch(() => {})
  }, SAVE_DELAY_MS)
}

/** Same document - one entry (an id is unique only within its DocType). */
const keyOf = (d: Pick<RecentDoc, 'doctype' | 'id'>) => `${d.doctype}\u0000${d.id}`

/**
 * Bring in the history from the server (other devices): merged with the local
 * one by time, newest first. Sends the result back when the local copy had
 * something the server didn't.
 */
export async function syncRecent(): Promise<void> {
  let all: Record<string, unknown>
  try {
    all = await viewSettingsApi.get(ANY_DOCTYPE)
  } catch {
    return // offline - the local copy stays
  }
  const remote = Array.isArray(all[VIEW]) ? (all[VIEW] as RecentDoc[]) : []
  const merged = new Map<string, RecentDoc>()
  for (const d of [...remote, ...read()].sort((a, b) => b.ts - a.ts)) {
    if (d?.doctype && d.id && !merged.has(keyOf(d))) merged.set(keyOf(d), d)
  }
  const next = [...merged.values()].slice(0, MAX)
  const changedRemote = JSON.stringify(next) !== JSON.stringify(remote.slice(0, MAX))
  write(next, { toServer: changedRemote })
}

/** Records a viewed document at the front of the list, de-duplicating by id. */
export function pushRecent(entry: Omit<RecentDoc, 'ts'>): void {
  const rest = read().filter((d) => keyOf(d) !== keyOf(entry))
  rest.unshift({ ...entry, ts: Date.now() })
  write(rest)
}

/** Removes a single entry (e.g. after it 404s). */
export function removeRecent(id: string): void {
  const entries = read()
  const next = entries.filter((d) => d.id !== id)
  if (next.length !== entries.length) write(next)
}

/**
 * Returns the history, dropping entries that point at workspaces that are no
 * longer installed. Rewrites storage only when something was actually pruned.
 */
export function readRecent(validWorkspaces: readonly string[]): RecentDoc[] {
  const valid = new Set(validWorkspaces)
  const entries = read()
  const kept = entries.filter((d) => valid.has(d.workspace))
  if (kept.length !== entries.length) write(kept)
  return kept
}

/** Heuristic: does this string look like an opaque id rather than a title? */
export function looksLikeId(value: string): boolean {
  // UUID (with dashes) or a bare hex hash of 8+ chars (Grunt's default names).
  return (
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value) ||
    /^[0-9a-f]{8,}$/i.test(value)
  )
}
