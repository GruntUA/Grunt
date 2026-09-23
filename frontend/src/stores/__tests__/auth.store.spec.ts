import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'

// ── Mocks ──────────────────────────────────────────────────────────────────

const { mockPost, mockGet, mockPatch } = vi.hoisted(() => ({
  mockPost: vi.fn(),
  mockGet: vi.fn(),
  mockPatch: vi.fn(),
}))

vi.mock('@/core/api/client', () => ({
  default: {
    post: mockPost,
    get: mockGet,
    patch: mockPatch,
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
}))

vi.mock('@/core/composables/useColorMode', () => ({
  useColorMode: () => ({ setTheme: vi.fn() }),
}))

// ── Fixtures ───────────────────────────────────────────────────────────────

const fakeUser = {
  id: 'usr-1',
  email: 'admin@grunt.local',
  full_name: 'Admin',
  roles: ['System Manager'],
  theme: 'system' as const,
}

const fakeTokenResponse = {
  access_token: 'fake-access-token',
  refresh_token: 'fake-refresh-token',
  token_type: 'bearer',
  user: fakeUser,
}

/** Wrap a payload in the standard {success, data} envelope, as the real API returns. */
function envelope<T>(data: T) {
  return { success: true, data }
}

// ── Tests ──────────────────────────────────────────────────────────────────

describe('useAuthStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    mockPost.mockReset()
    mockGet.mockReset()
    mockPatch.mockReset()
  })

  describe('initial state', () => {
    it('is not logged in by default', () => {
      const auth = useAuthStore()
      expect(auth.isLoggedIn).toBe(false)
    })

    it('reads token from localStorage', () => {
      localStorage.setItem('grunt_token', 'stored-token')
      const auth = useAuthStore()
      expect(auth.token).toBe('stored-token')
      expect(auth.isLoggedIn).toBe(true)
    })
  })

  describe('login', () => {
    it('sets token and user on success', async () => {
      mockPost.mockResolvedValueOnce({ data: envelope(fakeTokenResponse) })
      const auth = useAuthStore()
      await auth.login('admin@grunt.local', 'password')
      expect(auth.isLoggedIn).toBe(true)
      expect(auth.token).toBe('fake-access-token')
      expect(auth.refreshToken).toBe('fake-refresh-token')
      expect(auth.user?.email).toBe('admin@grunt.local')
    })

    it('persists tokens to localStorage', async () => {
      mockPost.mockResolvedValueOnce({ data: envelope(fakeTokenResponse) })
      const auth = useAuthStore()
      await auth.login('admin@grunt.local', 'password')
      expect(localStorage.getItem('grunt_token')).toBe('fake-access-token')
      expect(localStorage.getItem('grunt_refresh_token')).toBe('fake-refresh-token')
    })

    it('sends form-encoded body', async () => {
      mockPost.mockResolvedValueOnce({ data: envelope(fakeTokenResponse) })
      const auth = useAuthStore()
      await auth.login('user@test.com', 'pass123')
      expect(mockPost).toHaveBeenCalledWith(
        '/api/v1/method/grunt.auth.doctypes.User.user.login_api',
        { email: 'user@test.com', password: 'pass123' },
      )
    })

    it('throws on invalid credentials', async () => {
      mockPost.mockRejectedValueOnce({ response: { status: 401 } })
      const auth = useAuthStore()
      await expect(auth.login('bad@email.com', 'wrong')).rejects.toBeTruthy()
      expect(auth.isLoggedIn).toBe(false)
    })
  })

  describe('logout', () => {
    it('clears state and localStorage', async () => {
      mockPost.mockResolvedValueOnce({ data: envelope(fakeTokenResponse) })
      const auth = useAuthStore()
      await auth.login('admin@grunt.local', 'password')
      mockPost.mockResolvedValueOnce({ data: { success: true } }) // logout endpoint
      await auth.logout()
      expect(auth.isLoggedIn).toBe(false)
      expect(auth.token).toBeNull()
      expect(auth.user).toBeNull()
      expect(localStorage.getItem('grunt_token')).toBeNull()
    })

    it('clears state even if logout API fails', async () => {
      mockPost.mockResolvedValueOnce({ data: envelope(fakeTokenResponse) })
      const auth = useAuthStore()
      await auth.login('admin@grunt.local', 'password')
      mockPost.mockRejectedValueOnce(new Error('Network error'))
      await auth.logout()
      expect(auth.isLoggedIn).toBe(false)
    })
  })

  describe('refresh', () => {
    it('returns true and updates tokens on success', async () => {
      localStorage.setItem('grunt_refresh_token', 'old-refresh')
      mockPost.mockResolvedValueOnce({
        data: envelope({ ...fakeTokenResponse, access_token: 'new-access', refresh_token: 'new-refresh' }),
      })
      const auth = useAuthStore()
      const ok = await auth.refresh()
      expect(ok).toBe(true)
      expect(auth.token).toBe('new-access')
      expect(auth.refreshToken).toBe('new-refresh')
    })

    it('returns false when no refresh token stored', async () => {
      const auth = useAuthStore()
      const ok = await auth.refresh()
      expect(ok).toBe(false)
    })

    it('returns false and logs out on 401 response', async () => {
      localStorage.setItem('grunt_refresh_token', 'expired-token')
      mockPost.mockRejectedValueOnce({ response: { status: 401 } })
      const auth = useAuthStore()
      const ok = await auth.refresh()
      expect(ok).toBe(false)
      expect(auth.token).toBeNull()
    })

    it('adopts the pair another tab already refreshed instead of reusing the spent token', async () => {
      localStorage.setItem('grunt_token', 'expired-access')
      localStorage.setItem('grunt_refresh_token', 'spent-refresh')
      const auth = useAuthStore()

      // Another tab rotates the tokens while this one is waiting.
      const exp = Math.floor(Date.now() / 1000) + 600
      const fresh = `h.${btoa(JSON.stringify({ exp }))}.s`
      localStorage.setItem('grunt_token', fresh)
      localStorage.setItem('grunt_refresh_token', 'fresh-refresh')

      const ok = await auth.refresh()
      expect(ok).toBe(true)
      expect(mockPost).not.toHaveBeenCalled()
      expect(auth.token).toBe(fresh)
      expect(auth.refreshToken).toBe('fresh-refresh')
    })
  })

  describe('fetchMe', () => {
    it('populates user on success', async () => {
      localStorage.setItem('grunt_token', 'valid-token')
      localStorage.setItem('grunt_refresh_token', 'valid-refresh-token')
      mockGet.mockResolvedValueOnce({ data: fakeUser })
      const auth = useAuthStore()
      await auth.fetchMe()
      expect(auth.user?.email).toBe('admin@grunt.local')
    })

    it('logs out on fetch failure', async () => {
      localStorage.setItem('grunt_token', 'bad-token')
      mockGet.mockRejectedValueOnce(new Error('Unauthorized'))
      const auth = useAuthStore()
      await auth.fetchMe()
      expect(auth.isLoggedIn).toBe(false)
    })

    it('does nothing when no token', async () => {
      const auth = useAuthStore()
      await auth.fetchMe()
      expect(mockGet).not.toHaveBeenCalled()
    })
  })
})
