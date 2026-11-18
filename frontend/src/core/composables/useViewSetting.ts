/**
 * One of the user's list settings (FRAPPE_GAP_PLAN #6) - kept on the server per
 * DocType and view (grunt/api/v1/view_settings.py), so it follows the user
 * across devices; localStorage is only a cache:
 *
 * - the value starts from the cache (no flicker, works offline), then the
 *   server's value replaces it once loaded (one request per DocType);
 * - a change goes to the cache at once and to the server after a pause;
 * - `null` means "the defaults" - the server row is removed;
 * - nothing on the server yet but something cached (settings from before this
 *   was server-side) - the cached value is sent up once, so it isn't lost.
 */
import { ref, toRaw, watch, type Ref } from 'vue'
import { viewSettingsApi } from '@/core/api/viewSettings'

const SAVE_DELAY_MS = 800

// doctype -> the user's settings on the server, one request per DocType per page load.
const _loaded = new Map<string, Promise<Record<string, unknown>>>()

function serverSettings(doctype: string): Promise<Record<string, unknown>> {
  let pending = _loaded.get(doctype)
  if (!pending) {
    pending = viewSettingsApi.get(doctype).catch(() => {
      _loaded.delete(doctype) // offline / signed out - try again next time
      return {}
    })
    _loaded.set(doctype, pending)
  }
  return pending
}

// localStorage keys of the cached settings (the callers' cacheKey prefixes).
const CACHE_PREFIXES = [
  'grunt_columns_v2_',
  'grunt_quick_filters_v1_',
  'grunt_report_v1_',
  'grunt_list_prefs_',
  'grunt_recent_docs',
]

/**
 * Forget what was loaded. On a sign-out also the localStorage copies: the cache
 * belongs to the browser, not the user - the next user would otherwise start
 * from it (and have it sent up as theirs when their server copy is empty).
 */
export function clearViewSettingsCache(options: { local?: boolean } = {}): void {
  _loaded.clear()
  if (!options.local) return
  try {
    for (const key of Object.keys(localStorage)) {
      if (CACHE_PREFIXES.some((p) => key.startsWith(p))) localStorage.removeItem(key)
    }
  } catch {
    /* storage unavailable */
  }
}

function readCache<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : null
  } catch {
    return null
  }
}

function writeCache(key: string, value: unknown): void {
  try {
    if (value === null) localStorage.removeItem(key)
    else localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* quota / private mode - the server copy still counts */
  }
}

export interface ViewSettingOptions<T> {
  /** Drop a stored value of the wrong shape (an old format) instead of using it. */
  valid?: (value: unknown) => value is T
}

export function useViewSetting<T>(
  doctype: string,
  view: string,
  cacheKey: string,
  options: ViewSettingOptions<T> = {},
): Ref<T | null> {
  const accept = (v: unknown): T | null =>
    v === null || v === undefined ? null : !options.valid || options.valid(v) ? (v as T) : null

  const cached = accept(readCache<T>(cacheKey))
  const value = ref(cached) as Ref<T | null>
  let fromServer = false
  let timer: ReturnType<typeof setTimeout> | null = null

  void serverSettings(doctype).then((all) => {
    if (view in all) {
      const remote = accept(all[view])
      if (JSON.stringify(remote) !== JSON.stringify(value.value)) {
        fromServer = true
        value.value = remote
      }
    } else if (cached !== null && toRaw(value.value) === cached) {
      // Only the untouched cached value - a change made meanwhile is on its way already.
      void viewSettingsApi.save(doctype, view, cached).catch(() => {})
    }
  })

  watch(
    value,
    (next) => {
      writeCache(cacheKey, next)
      if (fromServer) {
        fromServer = false
        return
      }
      if (timer) clearTimeout(timer)
      timer = setTimeout(() => {
        timer = null
        void serverSettings(doctype).then((all) => {
          all[view] = next ?? undefined
          if (next === null) delete all[view]
        })
        void viewSettingsApi.save(doctype, view, next).catch(() => {})
      }, SAVE_DELAY_MS)
    },
    // sync: the cache is written with the change itself (a reload right after keeps it).
    { deep: true, flush: 'sync' },
  )

  return value
}
