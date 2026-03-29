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
  theme?: Theme
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('grunt_token'))
  const user = ref<User | null>(null)

  const isLoggedIn = computed(() => !!token.value)

  function applyUserTheme(u: User) {
    if (u.theme) useColorMode().setTheme(u.theme)
  }

  async function login(email: string, password: string) {
    const form = new URLSearchParams({ username: email, password })
    const { data } = await client.post('/api/v1/auth/token', form, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
    })
    token.value = data.access_token
    localStorage.setItem('grunt_token', data.access_token)
    user.value = data.user
    applyUserTheme(data.user)
  }

  async function fetchMe() {
    if (!token.value) return
    try {
      const { data } = await client.get('/api/v1/auth/me')
      const u = data.data ?? data
      user.value = u
      applyUserTheme(u)
    } catch {
      logout()
    }
  }

  async function setTheme(theme: Theme) {
    useColorMode().setTheme(theme)
    if (user.value) user.value.theme = theme
    await client.patch('/api/v1/auth/me', { theme })
  }

  function logout() {
    token.value = null
    user.value = null
    localStorage.removeItem('grunt_token')
  }

  return { token, user, isLoggedIn, login, logout, fetchMe, setTheme }
})
