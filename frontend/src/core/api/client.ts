import axios from 'axios'
import type { AxiosInstance, InternalAxiosRequestConfig } from 'axios'

// Backward-compat shim: backend no longer sends `id` (name is the sole PK).
// Recursively add `id = name` so existing components keep working unchanged.
function _normalizeIds(v: unknown): unknown {
  if (!v || typeof v !== 'object') return v
  if (Array.isArray(v)) return v.map(_normalizeIds)
  const obj = v as Record<string, unknown>
  const result: Record<string, unknown> = {}
  for (const k of Object.keys(obj)) {
    result[k] = typeof obj[k] === 'object' ? _normalizeIds(obj[k]) : obj[k]
  }
  if ('name' in result && !('id' in result) && result.name != null) {
    result.id = result.name
  }
  return result
}

const client: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  timeout: 30_000,
})

const MUTABLE_METHODS = new Set(['post', 'put', 'patch', 'delete'])
const PUBLIC_AUTH_PATHS = new Set([
  '/login',
  '/signup',
  '/forgot-password',
  '/reset-password',
  '/mfa-verify',
])

async function redirectToRoute(name: 'login' | 'forbidden') {
  const { default: router } = await import('@/router')
  window.location.href = router.resolve({ name }).href
}

function isPublicAuthPath(pathname: string): boolean {
  return PUBLIC_AUTH_PATHS.has(pathname)
}

// Request interceptor: attach Authorization header
client.interceptors.request.use(async (config) => {
  const { useAuthStore } = await import('@/stores/auth')
  const auth = useAuthStore()
  if (auth.token) {
    config.headers.Authorization = `Bearer ${auth.token}`
  }
  return config
})

// Track whether a refresh is in flight to avoid parallel refresh loops
let _refreshing: Promise<boolean> | null = null
let _lastForbiddenMessage: string | null = null
let _forbiddenToastReset: ReturnType<typeof setTimeout> | null = null

function showForbiddenToast(message: string) {
  if (message === _lastForbiddenMessage) return

  _lastForbiddenMessage = message
  if (_forbiddenToastReset) clearTimeout(_forbiddenToastReset)
  _forbiddenToastReset = setTimeout(() => {
    _lastForbiddenMessage = null
    _forbiddenToastReset = null
  }, 1_000)

  void import('@/core/composables/useToast').then(({ useToast }) => {
    useToast().error(message)
  })
}

// Response interceptor: normalize id=name shim, then handle auth errors
client.interceptors.response.use(
  (response) => {
    if (response.data && typeof response.data === 'object' && 'data' in response.data) {
      response.data.data = _normalizeIds(response.data.data)
    }
    return response
  },
  async (error) => {
    const originalConfig = error.config as InternalAxiosRequestConfig & { _retried?: boolean }
    const url = originalConfig?.url || ''

    // Skip auth endpoints to avoid infinite loops
    const isAuthEndpoint =
      url.includes('/auth/token') ||
      url.includes('/auth/register') ||
      url.includes('/auth/refresh') ||
      url.includes('/auth/logout') ||
      url.includes('/auth/mfa') ||
      url.includes('.User.user.login_api') ||
      url.includes('.User.user.refresh_api') ||
      url.includes('.User.user.logout_api') ||
      url.includes('.User.user.register_full_name_api') ||
      url.includes('.User.user.forgot_password_api') ||
      url.includes('.User.user.reset_password_api') ||
      url.includes('.User.user.mfa_login_api') ||
      url.includes('.User.user.verify_mfa')

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

      if (!isPublicAuthPath(window.location.pathname)) {
        await redirectToRoute('login')
      }
    }

    // Show toast for 403 forbidden responses — no redirect so the page and
    // network tab stay intact and the error is easy to debug.
    if (error.response?.status === 403) {
      const body = error.response?.data
      const message: string = body?.detail ?? body?.error?.message ?? 'Доступ заборонено'
      showForbiddenToast(message)
      return Promise.reject(error)
    }

    // Show error modal for 5xx server errors
    if (error.response?.status >= 500) {
      const body = error.response?.data
      const debug = body?.error?.debug ?? null
      const plainMessage = body?.error?.message ?? 'Server error. Please try again later.'
      if (debug) {
        const { useServerError } = await import('@/core/composables/useServerError')
        useServerError().show(error.response.status, debug, plainMessage)
      } else {
        const { useToast } = await import('@/core/composables/useToast')
        useToast().error(plainMessage)
      }
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
