import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import client from '@/core/api/client'
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

function _readImpersonation(): Impersonator | null {
  try {
    const raw = localStorage.getItem('grunt_impersonation')
    return raw ? (JSON.parse(raw) as Impersonator) : null
  } catch {
    return null
  }
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('grunt_token'))
  const refreshToken = ref<string | null>(localStorage.getItem('grunt_refresh_token'))
  const user = ref<User | null>(null)
  const isSystemManager = computed(() => !!user.value?.roles?.includes('System Manager'))

  // Set while a System Manager is viewing the system as another user. The real
  // session's tokens are stashed under `*_orig` keys and restored on stop.
  const impersonatedBy = ref<Impersonator | null>(_readImpersonation())
  const isImpersonating = computed(() => !!impersonatedBy.value)
  let _impTimer: ReturnType<typeof setTimeout> | null = null

  if (typeof window !== 'undefined') {
    window.addEventListener('storage', (e) => {
      if (e.key === 'grunt_token') {
        token.value = e.newValue
        if (!e.newValue) user.value = null
      } else if (e.key === 'grunt_refresh_token') {
        refreshToken.value = e.newValue
      }
    })
  }

  const isLoggedIn = computed(() => !!token.value)

  // Singleton promise so router guard and early init share one request
  let _fetchMePromise: Promise<void> | null = null

  function isJwtExpired(jwt: string): boolean {
    try {
      const payloadPart = jwt.split('.')[1]
      if (!payloadPart) return false
      const base64 = payloadPart.replace(/-/g, '+').replace(/_/g, '/')
      const json = atob(base64)
      const payload = JSON.parse(json)
      if (typeof payload?.exp !== 'number') return false
      // Consider a small skew window to avoid racing token expiry.
      return payload.exp * 1000 <= Date.now() + 5_000
    } catch {
      // Non-JWT token format: treat as non-expiring on client side.
      return false
    }
  }

  function applyUserPreferences(u: User) {
    if (u.theme) useColorMode().setTheme(u.theme)
    applyUserPrefs({ language: u.language, timezone: u.timezone })
  }

  function _setTokens(accessToken: string, rt: string) {
    token.value = accessToken
    refreshToken.value = rt
    localStorage.setItem('grunt_token', accessToken)
    localStorage.setItem('grunt_refresh_token', rt)
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
    if (data.access_token) {
      _setTokens(data.access_token, data.refresh_token)
      user.value = data.user
      applyUserPreferences(data.user)
    }
    return {
      mfa_required: !!data.mfa_required,
      approval_pending: !!data.approval_pending,
      mfa_token: data.mfa_token,
      expected_code: data.expected_code,
    }
  }

  /** Adopt a token pair minted server-side (e.g. the OAuth callback fragment). */
  async function setSession(accessToken: string, rt: string): Promise<void> {
    _setTokens(accessToken, rt)
    await fetchMe()
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
   * System Manager: open a short-lived session as `userId`. Stashes the real
   * session so `stopImpersonation()` can restore it, then swaps in the
   * impersonation access token (which has no refresh token - it just expires).
   */
  async function startImpersonation(userId: string): Promise<void> {
    const { authAdminApi } = await import('@/core/api/auth-admin')
    const data = await authAdminApi.startImpersonation(userId)

    if (token.value) localStorage.setItem('grunt_token_orig', token.value)
    if (refreshToken.value) localStorage.setItem('grunt_refresh_token_orig', refreshToken.value)

    token.value = data.access_token
    refreshToken.value = null
    localStorage.setItem('grunt_token', data.access_token)
    localStorage.removeItem('grunt_refresh_token')

    const who: Impersonator = {
      email: data.impersonated_by.email,
      full_name: data.impersonated_by.full_name,
    }
    impersonatedBy.value = who
    localStorage.setItem('grunt_impersonation', JSON.stringify(who))

    user.value = data.user as User
    applyUserPreferences(data.user as User)
    _scheduleImpersonationExpiry()
  }

  /** Leave an impersonation session and restore the System Manager's own session. */
  async function stopImpersonation(): Promise<void> {
    if (_impTimer) { clearTimeout(_impTimer); _impTimer = null }
    if (!isImpersonating.value) return

    try {
      const { authAdminApi } = await import('@/core/api/auth-admin')
      await authAdminApi.stopImpersonation()
    } catch {
      // best-effort audit call
    }

    const origToken = localStorage.getItem('grunt_token_orig')
    const origRefresh = localStorage.getItem('grunt_refresh_token_orig')
    localStorage.removeItem('grunt_token_orig')
    localStorage.removeItem('grunt_refresh_token_orig')
    localStorage.removeItem('grunt_impersonation')
    impersonatedBy.value = null

    if (origToken && origRefresh) {
      _setTokens(origToken, origRefresh)
      user.value = null
      await fetchMe()
    } else {
      _logout()
    }
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
    _setTokens(data.access_token, data.refresh_token)
    user.value = data.user
    applyUserPreferences(data.user)
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
    _setTokens(data.access_token, data.refresh_token)
    user.value = data.user
    applyUserPreferences(data.user)
    return { mfa_required: false, approval_pending: false }
  }

  /**
   * Swap the refresh token for a new pair. Refresh tokens are single-use and
   * shared by all tabs (localStorage), so the refresh is serialized across tabs:
   * a tab that waited for the lock adopts the pair another tab just minted
   * instead of spending the already-rotated token (which would log it out).
   */
  async function refresh(): Promise<boolean> {
    const staleAccess = token.value
    const run = () => _refreshOnce(staleAccess)
    return navigator.locks ? navigator.locks.request('grunt-token-refresh', run) : run()
  }

  async function _refreshOnce(staleAccess: string | null): Promise<boolean> {
    const storedAccess = localStorage.getItem('grunt_token')
    const rt = localStorage.getItem('grunt_refresh_token') ?? refreshToken.value
    if (!rt) return false
    if (storedAccess && storedAccess !== staleAccess && !isJwtExpired(storedAccess)) {
      token.value = storedAccess
      refreshToken.value = rt
      return true
    }
    try {
      const { data: body } = await client.post('/api/v1/method/grunt.auth.doctypes.User.user.refresh_api', {
        refresh_token: rt,
      })
      const data = body.data
      _setTokens(data.access_token, data.refresh_token)
      user.value = data.user
      applyUserPreferences(data.user)
      return true
    } catch (err: any) {
      // Only log out on auth errors (401/403), not on network/server errors
      if (err?.response?.status === 401 || err?.response?.status === 403) {
        _logout()
      }
      return false
    }
  }

  async function fetchMe() {
    if (!token.value) return

    if (isImpersonating.value) {
      // No refresh token by design - an expired impersonation token just ends.
      if (isJwtExpired(token.value)) {
        await stopImpersonation()
        return
      }
    } else {
      // Token without refresh token cannot be recovered and only causes noisy 401 calls.
      if (!refreshToken.value) {
        _logout()
        return
      }
      // Refresh first when access token is already expired.
      if (isJwtExpired(token.value)) {
        const ok = await refresh()
        if (!ok || user.value) return
      }
    }

    if (!_fetchMePromise) {
      _fetchMePromise = client.get('/api/v1/method/grunt.auth.doctypes.User.user.whoami')
        .then(({ data }) => {
          const u = data.data ?? data
          user.value = u
          applyUserPreferences(u)
          if (u.impersonated_by) {
            const who: Impersonator = {
              email: u.impersonated_by.email,
              full_name: u.impersonated_by.full_name,
            }
            impersonatedBy.value = who
            localStorage.setItem('grunt_impersonation', JSON.stringify(who))
            _scheduleImpersonationExpiry()
          }
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

  function prefetchMe() {
    if (token.value && !user.value) fetchMe()
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
    refreshToken.value = null
    user.value = null
    impersonatedBy.value = null
    localStorage.removeItem('grunt_token')
    localStorage.removeItem('grunt_refresh_token')
    localStorage.removeItem('grunt_token_orig')
    localStorage.removeItem('grunt_refresh_token_orig')
    localStorage.removeItem('grunt_impersonation')
    // Drop the user's timezone override; fall back to the site config.
    applyUserPrefs({})
  }

  async function logout() {
    try {
      await client.post('/api/v1/method/grunt.auth.doctypes.User.user.logout_api')
    } catch {
      // best-effort
    }
    _logout()
  }

  // Resume the expiry timer for an impersonation session across a page reload.
  if (isImpersonating.value) _scheduleImpersonationExpiry()

  return {
    token, refreshToken, user, isLoggedIn, isSystemManager, login, loginWithPasskey, beginEmailLogin,
    completeEmailLogin, setSession, logout, refresh, fetchMe, prefetchMe, setTheme, setLanguage,
    impersonatedBy, isImpersonating, startImpersonation, stopImpersonation,
  }
})
