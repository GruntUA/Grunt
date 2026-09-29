import axios from 'axios'
import { markServerReachable } from '@/core/composables/useNetworkStatus'
import type { AxiosInstance, InternalAxiosRequestConfig } from 'axios'
import i18n from '@/plugins/i18n'

const t = (key: string, params: Record<string, unknown> = {}): string => i18n.global.t(key, params)

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

// Request interceptor: attach Authorization header + current UI language
client.interceptors.request.use(async (config) => {
  const { useAuthStore } = await import('@/stores/auth')
  const auth = useAuthStore()
  if (auth.token) {
    config.headers.Authorization = `Bearer ${auth.token}`
  }
  try {
    const { i18n } = await import('@/plugins/i18n')
    config.headers['X-Grunt-Lang'] = i18n.global.locale.value
  } catch {
    // i18n not ready yet — server falls back to its default language
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
    // A real server answer, or the service worker's offline copy of one?
    markServerReachable(response.headers?.['x-grunt-offline'] !== '1')
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

      // An impersonation session has no refresh token — a 401 means it expired
      // or was rejected. Restore the System Manager's own session and retry once.
      {
        const { useAuthStore } = await import('@/stores/auth')
        const auth = useAuthStore()
        if (auth.isImpersonating) {
          await auth.stopImpersonation()
          const restored = localStorage.getItem('grunt_token')
          if (restored) {
            originalConfig.headers.Authorization = `Bearer ${restored}`
            return client(originalConfig)
          }
          if (!isPublicAuthPath(window.location.pathname)) {
            await redirectToRoute('login')
          }
          return Promise.reject(error)
        }
      }

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
      const message: string = body?.detail ?? body?.error?.message ?? t('Access denied')
      showForbiddenToast(message)
      return Promise.reject(error)
    }

    // Show the debug error modal for any response carrying a `debug` bundle —
    // not just 5xx. A backend bug can just as well surface as a 422 (e.g. a
    // pydantic model rejecting a shape the DB holds) or another status; what
    // matters is whether the server attached debug info (only happens with
    // settings.debug=True), not the status code itself.
    if (error.response?.status) {
      const body = error.response?.data
      const debug = body?.error?.debug ?? null
      const plainMessage = body?.error?.message ?? 'Server error. Please try again later.'
      if (debug) {
        const { useServerError } = await import('@/core/composables/useServerError')
        useServerError().show(error.response.status, debug, plainMessage)
      } else if (error.response.status >= 500) {
        const { useToast } = await import('@/core/composables/useToast')
        useToast().error(plainMessage)
      }
    }

    // Network error (no response): connection lost. A document create /
    // update / delete is queued for later (see useOfflineQueue); the caller
    // gets OfflineQueuedError instead of a response. Anything else (actions,
    // RPCs, login) just fails — replaying it later on stale state is unsafe.
    if (!error.response && error.request) {
      markServerReachable(false)
      const method = (originalConfig?.method ?? '').toLowerCase()
      const isReplay = originalConfig?.headers?.['X-Offline-Replay'] === '1'
      if (MUTABLE_METHODS.has(method) && !isReplay) {
        const { enqueue, OfflineQueuedError } = await import('@/core/composables/useOfflineQueue')
        const data = typeof originalConfig.data === 'string' ? JSON.parse(originalConfig.data) : originalConfig.data
        if (await enqueue(method, originalConfig.url ?? '', data)) {
          const { toast } = await import('@/core/composables/useToast')
          toast.info(t('Changes saved on this device — they will be sent once the connection is back'), t('No connection'))
          return Promise.reject(new OfflineQueuedError())
        }
      }
    }

    return Promise.reject(error)
  }
)

export default client
