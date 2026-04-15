import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import client from '@/core/api/client'
import { useColorMode, type Theme } from '@/core/composables/useColorMode'

interface User {
  id: string
  email: string
  full_name: string
  roles: string[]
  is_superadmin: boolean
  mfa_enabled?: boolean
  theme?: Theme
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('grunt_token'))
  const refreshToken = ref<string | null>(localStorage.getItem('grunt_refresh_token'))
  const user = ref<User | null>(null)

  const isLoggedIn = computed(() => !!token.value)

  function applyUserTheme(u: User) {
    if (u.theme) useColorMode().setTheme(u.theme)
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
    const form = new URLSearchParams({ username: email, password })
    const { data } = await client.post('/api/v1/auth/token', form, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
    })
    if (!data.mfa_required) {
      _setTokens(data.access_token, data.refresh_token)
      user.value = data.user
      applyUserTheme(data.user)
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
      const { data } = await client.post('/api/v1/auth/refresh', { refresh_token: rt })
      _setTokens(data.access_token, data.refresh_token)
      user.value = data.user
      return true
    } catch {
      _logout()
      return false
    }
  }

  async function fetchMe() {
    if (!token.value) return
    try {
      const { data } = await client.get('/api/v1/method/grunt.api.v1.user.whoami')
      const u = data.data ?? data
      user.value = u
      applyUserTheme(u)
    } catch {
      _logout()
    }
  }

  async function setTheme(theme: Theme) {
    useColorMode().setTheme(theme)
    if (user.value) user.value.theme = theme
    // We should patch this using grunt api if the user wants; for now we leave it or replace it.
    // Assuming there's an update method for user preferences, but since I didn't make a whitelisted method for setting theme, I'll keep the core endpoint or let it be.
    await client.patch('/api/v1/auth/me', { theme })
  }

  function _logout() {
    token.value = null
    refreshToken.value = null
    user.value = null
    localStorage.removeItem('grunt_token')
    localStorage.removeItem('grunt_refresh_token')
  }

  async function logout() {
    try {
      await client.post('/api/v1/auth/logout')
    } catch {
      // best-effort
    }
    _logout()
  }

  return { token, refreshToken, user, isLoggedIn, login, logout, refresh, fetchMe, setTheme }
})
