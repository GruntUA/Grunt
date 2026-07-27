// Client-side "recently viewed documents" history, persisted in localStorage.
//
// A single source of truth for the shape and the storage key so the writer
// (AppFormView) and the reader (DeskPage) cannot drift apart.

const KEY = 'grunt_recent_docs'
const MAX = 20
const CHANGED_EVENT = 'grunt_recent_docs_changed'

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

function write(entries: RecentDoc[]): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(entries.slice(0, MAX)))
    window.dispatchEvent(new Event(CHANGED_EVENT))
  } catch {
    // ignore quota / serialization errors — history is best-effort
  }
}

/** Records a viewed document at the front of the list, de-duplicating by id. */
export function pushRecent(entry: Omit<RecentDoc, 'ts'>): void {
  const rest = read().filter((d) => d.id !== entry.id)
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
