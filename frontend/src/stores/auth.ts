import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiClient } from '../core/api/client'
import { useRouter } from 'vue-router'

export const useAuthStore = defineStore('auth', () => {
    const token = ref<string | null>(localStorage.getItem('token'))
    const user = ref<any | null>(null)

    const login = async (credentials: any) => {
        // We send form data according to OAuth2 validation
        const formData = new URLSearchParams()
        formData.append('username', credentials.email)
        formData.append('password', credentials.password)

        const response = await apiClient.post<any, any>('/auth/token', formData, {
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        })

        token.value = response.access_token
        localStorage.setItem('token', response.access_token)
        await fetchUser()
    }

    const fetchUser = async () => {
        if (!token.value) return
        try {
            const response = await apiClient.get<any, any>('/auth/me')
            user.value = response
        } catch {
            logout()
        }
    }

    const logout = () => {
        token.value = null
        user.value = null
        localStorage.removeItem('token')
    }

    return { token, user, login, logout, fetchUser }
})
