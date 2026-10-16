import type { RouteLocationRaw } from 'vue-router'

/**
 * "Return to the page you came from" after signing in.
 *
 * The guard / 401 handler send the visitor to `/login?redirect=<path>`; the
 * login page stashes it in sessionStorage so it survives the MFA step and the
 * OAuth round-trip (which drops the query), and every successful sign-in
 * ends with `afterLoginTarget()`.
 */
const KEY = 'grunt_after_login'
const AUTH_PATHS = ['/login', '/signup', '/forgot-password', '/reset-password', '/mfa-verify']

/** Only same-origin app paths - never `//evil.com`, `/\evil.com` or an auth page. */
function isSafe(path: unknown): path is string {
  if (typeof path !== 'string' || !path.startsWith('/')) return false
  if (path.startsWith('//') || path.startsWith('/\\')) return false
  const bare = path.split(/[?#]/)[0]
  return bare !== '/' && !AUTH_PATHS.includes(bare)
}

export function loginLocation(fullPath?: string): RouteLocationRaw {
  return isSafe(fullPath) ? { name: 'login', query: { redirect: fullPath } } : { name: 'login' }
}

export function rememberLoginRedirect(path: unknown): void {
  if (!isSafe(path)) return
  try {
    sessionStorage.setItem(KEY, path)
  } catch {
    // storage blocked - fall back to the desk after login
  }
}

/** Where to go after a successful sign-in; consumes the stashed path. */
export function afterLoginTarget(): RouteLocationRaw {
  let path: string | null = null
  try {
    path = sessionStorage.getItem(KEY)
    sessionStorage.removeItem(KEY)
  } catch {
    // storage blocked
  }
  return isSafe(path) ? path : { name: 'desk' }
}
