import axios from 'axios'
import type { AxiosInstance } from 'axios'

const client: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000',
  timeout: 30_000,
})

// Request interceptor: додає Authorization header
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('grunt_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Response interceptor: 401 → redirect /login (skip auth endpoints)
client.interceptors.response.use(
  (response) => response,
  async (error) => {
    const url = error.config?.url || ''
    const isAuthEndpoint = url.includes('/auth/token') || url.includes('/auth/register')
    if (error.response?.status === 401 && !isAuthEndpoint) {
      localStorage.removeItem('grunt_token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default client
