/**
 * "Clear cache" for the current browser - drops what the client keeps between
 * page loads (translation bundle version, sidebar counts, the service worker's
 * response caches) and reloads, so schemas, menus and translations are fetched
 * fresh. User preferences, list layouts, form drafts, the session and the
 * offline edit queue are left alone.
 */
import { API_CACHE, SHELL_CACHE_PREFIX } from '@/core/browserHealth'

const LOCAL_CACHE_KEYS = ['grunt:sidebar-counts']
const LOCAL_CACHE_PREFIXES = ['grunt-locale-version:']

export async function clearClientCache(): Promise<void> {
  try {
    for (const key of Object.keys(localStorage)) {
      if (LOCAL_CACHE_KEYS.includes(key) || LOCAL_CACHE_PREFIXES.some((p) => key.startsWith(p))) {
        localStorage.removeItem(key)
      }
    }
  } catch {
    // storage unavailable - nothing cached there
  }

  if ('caches' in window) {
    const names = await caches.keys()
    await Promise.all(
      names
        .filter((n) => n === API_CACHE || n.startsWith(SHELL_CACHE_PREFIX))
        .map((n) => caches.delete(n)),
    )
  }

  window.location.reload()
}
