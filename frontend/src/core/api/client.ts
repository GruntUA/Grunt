import axios from 'axios'
import type { AxiosInstance, InternalAxiosRequestConfig } from 'axios'

const client: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  timeout: 30_000,
})

const MUTABLE_METHODS = new Set(['post', 'put', 'patch', 'delete'])

// Request interceptor: attach Authorization header
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('grunt_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Track whether a refresh is in flight to avoid parallel refresh loops
let _refreshing: Promise<boolean> | null = null

// Response interceptor: on 401, try to refresh once, then redirect to login
client.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalConfig = error.config as InternalAxiosRequestConfig & { _retried?: boolean }
    const url = originalConfig?.url || ''

    // Skip auth endpoints to avoid infinite loops
    const isAuthEndpoint =
      url.includes('/auth/token') ||
      url.includes('/auth/register') ||
      url.includes('/auth/refresh') ||
      url.includes('/auth/logout')

    if (error.response?.status === 401 && !isAuthEndpoint && !originalConfig._retried) {
      originalConfig._retried = true

      // Coalesce concurrent refresh attempts into one
      if (!_refreshing) {
        _refreshing = (async () => {
          const { useAuthStore } = await import('@/stores/auth')
          const auth = useAuthStore()
          return auth.refresh()
        })().finally(() => { _refreshing = null })
      }

      const ok = await _refreshing
      if (ok) {
        // Retry original request with new token
        const newToken = localStorage.getItem('grunt_token')
        if (newToken) originalConfig.headers.Authorization = `Bearer ${newToken}`
        return client(originalConfig)
      }

      window.location.href = '/login'
    }

    // Redirect to 403 page on forbidden responses
    if (error.response?.status === 403) {
      window.location.href = '/403'
      return Promise.reject(error)
    }

    // Show toast for 5xx server errors
    if (error.response?.status >= 500) {
      const { useToast } = await import('@/core/composables/useToast')
      useToast().error('Server error. Please try again later.')
    }

    // Network error (no response): connection lost
    if (!error.response && error.request) {
      const method = (originalConfig?.method ?? '').toLowerCase()

      // Don't enqueue replayed requests or GET requests
      const isReplay = originalConfig?.headers?.['X-Offline-Replay'] === '1'
      if (MUTABLE_METHODS.has(method) && !isReplay) {
        // Silently enqueue the mutation for later replay
        const { offlineQueue } = await import('@/core/composables/useOfflineQueue')
        const token = localStorage.getItem('grunt_token')
        await offlineQueue.enqueue({
          method: originalConfig.method ?? 'post',
          url: originalConfig.url ?? '',
          data: originalConfig.data ? JSON.parse(originalConfig.data) : undefined,
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        })
        // Return a resolved placeholder so the UI doesn't crash
        return Promise.resolve({ data: { _queued: true }, status: 202, statusText: 'Queued' })
      }
    }

    return Promise.reject(error)
  }
)

export default client
