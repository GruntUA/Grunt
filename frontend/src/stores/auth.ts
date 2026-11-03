import { defineStore } from 'pinia'
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

// Tabs tell each other about a sign-in or sign-out: they share the session cookie.
type AuthMessage = { type: 'login' } | { type: 'logout' }

export const useAuthStore = defineStore('auth', () => {
  const token = accessToken
  const user = ref<User | null>(null)
  const isSystemManager = computed(() => !!user.value?.roles?.includes('System Manager'))

  // Set while a System Manager is viewing the system as another user.
  const impersonatedBy = ref<Impersonator | null>(null)
  const isImpersonating = computed(() => !!impersonatedBy.value)
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

  async function login(email: string, password: string): Promise<{
    mfa_required: boolean
    approval_pending: boolean
    mfa_token?: string
    expected_code?: string
  }> {
    const { data: body } = await client.post('/api/v1/method/grunt.auth.doctypes.User.user.login_api', {
      email,
      password,
    })
    const data = body.data
    if (data.access_token) adoptLogin(data)
    return {
      mfa_required: !!data.mfa_required,
      approval_pending: !!data.approval_pending,
      mfa_token: data.mfa_token,
      expected_code: data.expected_code,
    }
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
  async function startImpersonation(userId: string): Promise<void> {
    const { authAdminApi } = await import('@/core/api/auth-admin')
    const data = await authAdminApi.startImpersonation(userId)

    const by: Impersonator = {
      email: data.impersonated_by.email,
      full_name: data.impersonated_by.full_name,
    }
    _writeImpersonation({ token: data.access_token, by })
    impersonatedBy.value = by
    _adopt({ access_token: data.access_token, user: data.user as User })
    _scheduleImpersonationExpiry()
  }

  /** Leave an impersonation session and go back to the System Manager's own session. */
  async function stopImpersonation(): Promise<void> {
    if (_impTimer) { clearTimeout(_impTimer); _impTimer = null }
    if (!isImpersonating.value) return

    try {
      const { authAdminApi } = await import('@/core/api/auth-admin')
      await authAdminApi.stopImpersonation()
    } catch {
      // best-effort audit call
    }

    _writeImpersonation(null)
    impersonatedBy.value = null
    token.value = null
    user.value = null
    if (!(await refresh())) _logout()
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
      const err: any = new Error('mfa_required')
      err.mfa = { mfa_token: data.mfa_token, user: data.user }
      throw err
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
      const { data: body } = await client.post('/api/v1/method/grunt.auth.doctypes.User.user.refresh_api')
      _adopt(body.data)
      return 'ok'
    } catch (err: any) {
      const status = err?.response?.status
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
      _fetchMePromise = client.get('/api/v1/method/grunt.auth.doctypes.User.user.whoami')
        .then(({ data }) => {
          const u = data.data ?? data
          user.value = u
          applyUserPreferences(u)
        })
        .catch((err: any) => {
          if (isImpersonating.value) {
            void stopImpersonation()
          } else if (err?.response?.status === 401 || err?.response?.status === 403) {
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
    await client.post('/api/v1/method/grunt.auth.doctypes.User.user.update_me_api', { theme })
  }

  async function setLanguage(language: SupportedLocale) {
    setLocale(language)
    if (user.value) user.value.language = language
    await client.post('/api/v1/method/grunt.auth.doctypes.User.user.update_me_api', { language })
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
  }

  async function logout() {
    try {
      // Ends the session the cookie names and clears the cookie.
      await client.post('/api/v1/method/grunt.auth.doctypes.User.user.logout_api')
    } catch {
      // best-effort
    }
    _logout()
    channel?.postMessage({ type: 'logout' } satisfies AuthMessage)
  }

  return {
    token, user, isLoggedIn, isSystemManager, restore, login, adoptLogin, loginWithPasskey,
    beginEmailLogin, completeEmailLogin, logout, refresh, fetchMe, setTheme, setLanguage,
    impersonatedBy, isImpersonating, startImpersonation, stopImpersonation,
  }
})
