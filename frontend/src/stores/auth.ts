import { defineStore } from 'pinia'
import { clearViewSettingsCache } from '@/core/composables/useViewSetting'
import { ref, computed } from 'vue'
import client from '@/core/api/client'
import { accessToken } from '@/core/accessToken'
import { isJwtExpired } from '@/core/jwt'
import { useColorMode, type Theme } from '@/core/composables/useColorMode'
import { applyUserPrefs } from '@/core/composables/useSiteConfig'
import { setLocale, type SupportedLocale } from '@/plugins/i18n'
import i18n from '@/plugins/i18n'

const t = (key: string, params: Record<string, unknown> = {}): string => i18n.global.t(key, params)

interface User {
  id: string
  email: string
  full_name: string
  roles: string[]
  /** Permissions through the roles (grunt.permissions.perms); `*` - all. */
  permissions?: string[]
  /** Every role is site-only (Role.site_only): the website, not the workspace. */
  site_only?: boolean
  /** Where to land after signing in (Role.home_page). */
  home_page?: string | null
  mfa_enabled?: boolean
  /** False for accounts provisioned via OIDC / email link that never set one. */
  has_password?: boolean
  theme?: Theme
  avatar?: string
  language?: string
  timezone?: string
}

interface Impersonator {
  email: string
  full_name: string
}

interface LoginPayload {
  access_token: string
  user: User
}

/**
 * An impersonation session of this tab: its access token and who opened it.
 * Per tab (sessionStorage) and short-lived, so it survives a reload of the tab;
 * the System Manager's own session stays in the cookie meanwhile.
 */
const IMPERSONATION_KEY = 'grunt_impersonation'

interface Impersonation {
  token: string
  by: Impersonator
  /** The page the System Manager started from - where switching back returns. */
  from?: string
}

function _readImpersonation(): Impersonation | null {
  try {
    const raw = sessionStorage.getItem(IMPERSONATION_KEY)
    return raw ? (JSON.parse(raw) as Impersonation) : null
  } catch {
    return null
  }
}

function _writeImpersonation(value: Impersonation | null) {
  try {
    if (value) sessionStorage.setItem(IMPERSONATION_KEY, JSON.stringify(value))
    else sessionStorage.removeItem(IMPERSONATION_KEY)
  } catch {
    // storage blocked - the impersonation just ends with a reload
  }
}

/** `path` if it is a same-origin path, else null. Not `//host`, a full URL,
 *  or `/\host` (the URL parser reads `\` as `/`); no control characters
 *  (the parser drops tabs and newlines). The parsed URL must stay on this origin,
 *  and its normalised path must not start with `//`. */
function _localPath(path: string | undefined): string | null {
  if (!path || !path.startsWith('/') || path.includes('\\')) return null
  if ([...path].some((ch) => ch.charCodeAt(0) < 0x20 || ch.charCodeAt(0) === 0x7f)) return null
  try {
    const url = new URL(path, window.location.origin)
    // Dot segments may normalise `/.//host/x` to `//host/x` - another host once reparsed.
    if (url.origin !== window.location.origin || url.pathname.startsWith('//')) return null
    return url.pathname + url.search + url.hash
  } catch {
    return null
  }
}

/** Full reload at `path` (or `/`) - also when only its `#fragment` differs
 *  from the current page, which would otherwise not reload. */
export function reloadAt(path: string | null) {
  const url = new URL(_localPath(path ?? undefined) ?? '/', window.location.origin)
  const here = window.location
  if (url.pathname === here.pathname && url.search === here.search) {
    history.replaceState(history.state, '', url.pathname + url.search + url.hash)
    here.reload()
  } else {
    here.href = url.pathname + url.search + url.hash
  }
}

/** The HTTP status of a failed request, if it got an answer. */
function _httpStatus(err: unknown): number | undefined {
  return (err as { response?: { status?: number } } | null)?.response?.status
}

// Tabs tell each other about a sign-in or sign-out: they share the session cookie.
type AuthMessage = { type: 'login' } | { type: 'logout' }

export const useAuthStore = defineStore('auth', () => {
  const token = accessToken
  const user = ref<User | null>(null)
  /** Whether the user holds permission `name` (`*` holds them all). */
  function hasPerm(name: string): boolean {
    const held = user.value?.permissions ?? []
    return held.includes('*') || held.includes(name)
  }

  // Set while a System Manager is viewing the system as another user.
  const impersonatedBy = ref<Impersonator | null>(null)
  const isImpersonating = computed(() => !!impersonatedBy.value)
  let _impFrom: string | null = null
  let _impTimer: ReturnType<typeof setTimeout> | null = null

  // Signed in, or offline with the profile the service worker cached: the
  // access token comes with the first refresh once the server is reachable.
  const isLoggedIn = computed(() => !!token.value || !!user.value)

  const channel = typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel('grunt-auth') : null
  channel?.addEventListener('message', (e: MessageEvent<AuthMessage>) => {
    if (e.data.type === 'logout') _logout()
    else if (e.data.type === 'login' && !isImpersonating.value) void refresh()
  })

  // Singleton promise so router guard and early init share one request
  let _fetchMePromise: Promise<void> | null = null
  let _restorePromise: Promise<void> | null = null

  function applyUserPreferences(u: User) {
    if (u.theme) useColorMode().setTheme(u.theme)
    applyUserPrefs({ language: u.language, timezone: u.timezone })
  }

  function _adopt(data: LoginPayload) {
    token.value = data.access_token
    user.value = data.user
    applyUserPreferences(data.user)
  }

  /** A sign-in that just completed in this tab (its response set the session cookie). */
  function adoptLogin(data: LoginPayload) {
    _adopt(data)
    channel?.postMessage({ type: 'login' } satisfies AuthMessage)
  }

  /**
   * Pick up the session on page load: this tab's impersonation, else the
   * session cookie. Offline, the profile comes from the service worker's copy
   * of `whoami`. The router guard awaits it before the first route.
   */
  function restore(): Promise<void> {
    _restorePromise ??= (async () => {
      const imp = _readImpersonation()
      if (imp && !isJwtExpired(imp.token)) {
        token.value = imp.token
        impersonatedBy.value = imp.by
        _impFrom = _localPath(imp.from)
        _scheduleImpersonationExpiry()
        await fetchMe()
        return
      }
      _writeImpersonation(null)
      const outcome = await _refreshOutcome()
      if (outcome === 'offline') await fetchMe()
    })()
    return _restorePromise
  }

  /** What a sign-in step answers: done, or the next step it asks for. */
  interface LoginStep {
    mfa_required: boolean
    approval_pending: boolean
    mfa_token?: string
    expected_code?: string
    /** The password has expired - set a new one (changeExpiredPassword) first. */
    password_change_required?: boolean
    password_change_token?: string
  }

  /** A sign-in answer: the session (`access_token` + `user`) or the next step. */
  type LoginAnswer = Partial<LoginPayload> & Partial<LoginStep>

  function _loginStep(data: LoginAnswer): LoginStep {
    if (data.access_token) adoptLogin(data as LoginPayload)
    return {
      mfa_required: !!data.mfa_required,
      approval_pending: !!data.approval_pending,
      mfa_token: data.mfa_token,
      expected_code: data.expected_code,
      password_change_required: !!data.password_change_required,
      password_change_token: data.password_change_token,
    }
  }

  async function login(email: string, password: string): Promise<LoginStep> {
    const { data: body } = await client.post('/api/v1/method/grunt.auth.user_api.login_api', {
      email,
      password,
    })
    return _loginStep(body.data)
  }

  /** An expired password: set the new one and go on with the sign-in (MFA next, if any). */
  async function changeExpiredPassword(token: string, newPassword: string): Promise<LoginStep> {
    const { data: body } = await client.post(
      '/api/v1/method/grunt.auth.user_api.change_expired_password_api',
      { password_change_token: token, new_password: newPassword },
    )
    return _loginStep(body.data)
  }

  function _jwtExpMs(jwt: string): number | null {
    try {
      const payload = JSON.parse(atob(jwt.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
      return typeof payload?.exp === 'number' ? payload.exp * 1000 : null
    } catch {
      return null
    }
  }

  function _scheduleImpersonationExpiry() {
    if (_impTimer) clearTimeout(_impTimer)
    if (!token.value) return
    const expMs = _jwtExpMs(token.value)
    if (expMs == null) return
    const delay = Math.max(0, expMs - Date.now())
    _impTimer = setTimeout(() => { void stopImpersonation() }, delay)
  }

  /**
   * System Manager: open a short-lived session as `userId` in this tab. Its
   * access token has no refresh - it just expires; the System Manager's own
   * session stays in the cookie for `stopImpersonation()`.
   */
  async function startImpersonation(userId: string, from?: string): Promise<void> {
    const { authAdminApi } = await import('@/core/api/auth-admin')
    const data = await authAdminApi.startImpersonation(userId)

    const by: Impersonator = {
      email: data.impersonated_by.email,
      full_name: data.impersonated_by.full_name,
    }
    _writeImpersonation({ token: data.access_token, by, from })
    impersonatedBy.value = by
    _impFrom = _localPath(from)
    _adopt({ access_token: data.access_token, user: data.user as User })
    _scheduleImpersonationExpiry()
  }

  /**
   * Leave an impersonation session and go back to the System Manager's own
   * session. Returns the page the impersonation started from, if known.
   */
  async function stopImpersonation(): Promise<string | null> {
    if (_impTimer) { clearTimeout(_impTimer); _impTimer = null }
    if (!isImpersonating.value) return null
    const from = _impFrom

    try {
      const { authAdminApi } = await import('@/core/api/auth-admin')
      await authAdminApi.stopImpersonation()
    } catch {
      // best-effort audit call
    }

    _writeImpersonation(null)
    impersonatedBy.value = null
    _impFrom = null
    token.value = null
    user.value = null
    if (!(await refresh())) _logout()
    return from
  }

  async function loginWithPasskey(
    email?: string,
    opts?: { mode?: 'cross-device' },
  ): Promise<void> {
    const { authApi } = await import('@/core/api/auth')
    const { getPasskeyAssertion, isWebAuthnSupported } = await import('@/core/composables/useWebAuthn')
    if (!isWebAuthnSupported()) throw new Error(t('This browser does not support passkeys'))

    const payload: Record<string, string> = {}
    if (opts?.mode) payload.mode = opts.mode
    else if (email) payload.email = email
    const { options, challenge_token } = await authApi.begin('webauthn', payload)
    const assertion = await getPasskeyAssertion(options)
    const data = await authApi.complete('webauthn', {
      challenge_token,
      response: assertion,
    })

    if (data.approval_pending) throw new Error('approval_pending')
    if (data.mfa_required) {
      // Rare: user has MFA on top of a passkey - hand back to the MFA step.
      throw Object.assign(new Error('mfa_required'), {
        mfa: { mfa_token: data.mfa_token, user: data.user },
      })
    }
    adoptLogin(data)
  }

  /** Passwordless "sign in with email" - step 1: mail a code + magic link. */
  async function beginEmailLogin(
    email: string,
  ): Promise<{ challenge_token: string; ttl_minutes: number }> {
    const { authApi } = await import('@/core/api/auth')
    return authApi.begin('email', { email })
  }

  /**
   * Passwordless "sign in with email" - step 2. Pass the mailed `code` together
   * with the `challenge_token` from step 1, or the `token` lifted from a magic
   * link. Adopts the session on success.
   */
  async function completeEmailLogin(
    payload: { challenge_token: string; code: string } | { token: string },
  ): Promise<{ mfa_required: boolean; approval_pending: boolean; mfa_token?: string }> {
    const { authApi } = await import('@/core/api/auth')
    const data = await authApi.complete('email', payload as Record<string, unknown>)
    if (data.approval_pending) return { mfa_required: false, approval_pending: true }
    if (data.mfa_required) {
      return { mfa_required: true, approval_pending: false, mfa_token: data.mfa_token }
    }
    adoptLogin(data)
    return { mfa_required: false, approval_pending: false }
  }

  /**
   * A new access token for the session cookie. The server rotates the cookie
   * on the way, so refreshes are serialized across the tabs sharing it; a tab
   * that waited keeps a token another caller in it got meanwhile.
   */
  async function refresh(): Promise<boolean> {
    return (await _refreshOutcome()) === 'ok'
  }

  type RefreshOutcome = 'ok' | 'signed-out' | 'offline'

  async function _refreshOutcome(): Promise<RefreshOutcome> {
    // An impersonation token cannot be renewed - it ends instead.
    if (isImpersonating.value) return 'signed-out'
    const staleAccess = token.value
    const run = () => _refreshOnce(staleAccess)
    return navigator.locks ? navigator.locks.request('grunt-token-refresh', run) : run()
  }

  async function _refreshOnce(staleAccess: string | null): Promise<RefreshOutcome> {
    if (token.value && token.value !== staleAccess && !isJwtExpired(token.value)) return 'ok'
    try {
      const { data: body } = await client.post('/api/v1/method/grunt.auth.user_api.refresh_api')
      _adopt(body.data)
      return 'ok'
    } catch (err: unknown) {
      const status = _httpStatus(err)
      // Only log out on auth errors (401/403), not on network/server errors
      if (status === 401 || status === 403) {
        _logout()
        return 'signed-out'
      }
      return status ? 'signed-out' : 'offline'
    }
  }

  async function fetchMe() {
    if (isImpersonating.value && token.value && isJwtExpired(token.value)) {
      await stopImpersonation()
      return
    }

    if (!_fetchMePromise) {
      _fetchMePromise = client.get('/api/v1/method/grunt.auth.user_api.whoami')
        .then(({ data }) => {
          const u = data.data ?? data
          user.value = u
          applyUserPreferences(u)
        })
        .catch((err: unknown) => {
          const status = _httpStatus(err)
          if (isImpersonating.value) {
            void stopImpersonation()
          } else if (status === 401 || status === 403) {
            // Only log out on auth errors (401/403), not on network/server errors
            _logout()
          }
        })
        .finally(() => { _fetchMePromise = null })
    }
    return _fetchMePromise
  }

  async function setTheme(theme: Theme) {
    useColorMode().setTheme(theme)
    if (user.value) user.value.theme = theme
    await client.post('/api/v1/method/grunt.auth.user_api.update_me_api', { theme })
  }

  async function setLanguage(language: SupportedLocale) {
    setLocale(language)
    if (user.value) user.value.language = language
    await client.post('/api/v1/method/grunt.auth.user_api.update_me_api', { language })
  }

  function _logout() {
    if (_impTimer) { clearTimeout(_impTimer); _impTimer = null }
    // The service worker's offline copy of API responses is this user's data.
    if (typeof caches !== 'undefined') caches.delete('grunt-api-v1').catch(() => undefined)
    token.value = null
    user.value = null
    impersonatedBy.value = null
    _writeImpersonation(null)
    // Drop the user's timezone override; fall back to the site config.
    applyUserPrefs({})
    // Their list settings (server-side now, cached in this browser).
    clearViewSettingsCache({ local: true })
  }

  async function logout() {
    try {
      // Ends the session the cookie names and clears the cookie.
      await client.post('/api/v1/method/grunt.auth.user_api.logout_api')
    } catch {
      // best-effort
    }
    _logout()
    channel?.postMessage({ type: 'logout' } satisfies AuthMessage)
  }

  return {
    token, user, isLoggedIn, hasPerm, restore, login, changeExpiredPassword, adoptLogin, loginWithPasskey,
    beginEmailLogin, completeEmailLogin, logout, refresh, fetchMe, setTheme, setLanguage,
    impersonatedBy, isImpersonating, startImpersonation, stopImpersonation,
  }
})
