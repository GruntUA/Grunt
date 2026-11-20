import type { RouteLocationRaw, Router } from 'vue-router'

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

/**
 * A same-origin path: never `//evil.com` or `/\\evil.com`, and no tab, line
 * break or backslash anywhere (browsers drop the first two, so `/\t/evil.com`
 * would turn into `//evil.com`).
 */
function isLocalPath(path: unknown): path is string {
  if (typeof path !== 'string' || !path.startsWith('/')) return false
  return !path.startsWith('//') && !/[\t\n\r\\]/.test(path)
}

/** A path to come back to after signing in - not the bare root nor an auth page. */
function isSafe(path: unknown): path is string {
  if (!isLocalPath(path)) return false
  const bare = path.split(/[?#]/)[0]
  return bare !== '/' && !AUTH_PATHS.includes(bare)
}

/** A home page (``Role.home_page``): any local path but an auth page - the site root too. */
function isSafeHome(path: unknown): path is string {
  return isLocalPath(path) && !AUTH_PATHS.includes(path.split(/[?#]/)[0])
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

function takeStashed(): string | null {
  let path: string | null = null
  try {
    path = sessionStorage.getItem(KEY)
    sessionStorage.removeItem(KEY)
  } catch {
    // storage blocked
  }
  return isSafe(path) ? path : null
}

/**
 * Where in the SPA to go after a successful sign-in: the stashed path
 * (consumed), else the user's *home* page (``Role.home_page``), else the desk.
 */
export function afterLoginTarget(home?: string | null): RouteLocationRaw {
  return takeStashed() ?? (isSafeHome(home) ? home : { name: 'desk' })
}

/** A path the SPA has a page for - anything else (the website) needs a full page load. */
export function isSpaPath(router: Router, path: string): boolean {
  const name = router.resolve(path).name
  return name !== undefined && name !== 'not-found'
}

/**
 * The user's home page when it is on the website (outside the SPA) and no
 * stashed path takes precedence - to open with a full page load. Only the
 * server-given home page ever leaves the SPA: a stashed path comes from the
 * URL and stays in the router.
 */
export function websiteHome(router: Router, home?: string | null): string | null {
  let stashed = false
  try {
    stashed = isSafe(sessionStorage.getItem(KEY))
  } catch {
    // storage blocked
  }
  return !stashed && isSafeHome(home) && !isSpaPath(router, home) ? home : null
}

/** Sign-in finished: the website home page with a full load, else :func:`afterLoginTarget`. */
export function goAfterLogin(router: Router, home?: string | null): void {
  const site = websiteHome(router, home)
  if (site) window.location.assign(site)
  else void router.push(afterLoginTarget(home))
}
