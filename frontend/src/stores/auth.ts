import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import client from '@/core/api/client'

interface User {
  id: string
  email: string
  full_name: string
  roles: string[]
  is_superadmin: boolean
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('grunt_token'))
  const user = ref<User | null>(null)

  const isLoggedIn = computed(() => !!token.value)

  async function login(email: string, password: string) {
    const form = new URLSearchParams({ username: email, password })
    const { data } = await client.post('/api/v1/auth/token', form, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
    })
    token.value = data.access_token
    localStorage.setItem('grunt_token', data.access_token)
    user.value = data.user
  }

  async function fetchMe() {
    if (!token.value) return
    const { data } = await client.get('/api/v1/auth/me')
    user.value = data.data
  }

  function logout() {
    token.value = null
    user.value = null
    localStorage.removeItem('grunt_token')
  }

  return { token, user, isLoggedIn, login, logout, fetchMe }
})
