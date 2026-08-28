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
    mfa_token?: string
    expected_code?: string
  }> {
    const { data: body } = await client.post('/api/v1/method/grunt.auth.doctypes.User.user.login_api', {
      email,
      password,
    })
    const data = body.data
    if (!data.mfa_required) {
      _setTokens(data.access_token, data.refresh_token)
      user.value = data.user
      applyUserPreferences(data.user)
    }
    return {
      mfa_required: !!data.mfa_required,
      mfa_token: data.mfa_token,
      expected_code: data.expected_code,
    }
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

  return { token, refreshToken, user, isLoggedIn, login, logout, refresh, fetchMe, prefetchMe, setTheme, setLanguage }
})
