import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import client from '@/core/api/client'
import { useColorMode, type Theme } from '@/core/composables/useColorMode'
import { applyUserPrefs } from '@/core/composables/useSiteConfig'
import { setLocale, type SupportedLocale } from '@/plugins/i18n'

interface User {
  id: string
  email: string
  full_name: string
  roles: string[]
  is_superadmin: boolean
  mfa_enabled?: boolean
  theme?: Theme
  avatar?: string
  language?: string
  timezone?: string
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('grunt_token'))
  const refreshToken = ref<string | null>(localStorage.getItem('grunt_refresh_token'))
  const user = ref<User | null>(null)

  if (typeof window !== 'undefined') {
    window.addEventListener('storage', (e) => {
      if (e.key === 'grunt_token') {
        token.value = e.newValue
        if (!e.newValue) user.value = null
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

  async function loginWithPasskey(
    email?: string,
    opts?: { mode?: 'cross-device' },
  ): Promise<void> {
    const { authApi } = await import('@/core/api/auth')
    const { getPasskeyAssertion, isWebAuthnSupported } = await import('@/core/composables/useWebAuthn')
    if (!isWebAuthnSupported()) throw new Error('Цей браузер не підтримує ключі доступу')

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
      // Rare: user has MFA on top of a passkey — hand back to the MFA step.
      const err: any = new Error('mfa_required')
      err.mfa = { mfa_token: data.mfa_token, user: data.user }
      throw err
    }
    _setTokens(data.access_token, data.refresh_token)
    user.value = data.user
    applyUserPreferences(data.user)
  }

  /** Passwordless "sign in with email" — step 1: mail a code + magic link. */
  async function beginEmailLogin(
    email: string,
  ): Promise<{ challenge_token: string; ttl_minutes: number }> {
    const { authApi } = await import('@/core/api/auth')
    return authApi.begin('email', { email })
  }

  /**
   * Passwordless "sign in with email" — step 2. Pass the mailed `code` together
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

  async function refresh(): Promise<boolean> {
    const rt = refreshToken.value
    if (!rt) return false
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

    if (!_fetchMePromise) {
      _fetchMePromise = client.get('/api/v1/method/grunt.auth.doctypes.User.user.whoami')
        .then(({ data }) => {
          const u = data.data ?? data
          user.value = u
          applyUserPreferences(u)
        })
        .catch((err: any) => {
          // Only log out on auth errors (401/403), not on network/server errors
          if (err?.response?.status === 401 || err?.response?.status === 403) {
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
    token.value = null
    refreshToken.value = null
    user.value = null
    localStorage.removeItem('grunt_token')
    localStorage.removeItem('grunt_refresh_token')
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

  return { token, refreshToken, user, isLoggedIn, login, loginWithPasskey, beginEmailLogin, completeEmailLogin, setSession, logout, refresh, fetchMe, prefetchMe, setTheme, setLanguage }
})
