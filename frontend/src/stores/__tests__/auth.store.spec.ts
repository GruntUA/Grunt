import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import { accessToken } from '@/core/accessToken'

// Mocks

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

// Fixtures

const fakeUser = {
  id: 'usr-1',
  email: 'admin@grunt.local',
  full_name: 'Admin',
  roles: ['System Manager'],
  theme: 'system' as const,
}

const fakeTokenResponse = {
  access_token: 'fake-access-token',
  token_type: 'bearer',
  user: fakeUser,
}

/** Wrap a payload in the standard {success, data} envelope, as the real API returns. */
function envelope<T>(data: T) {
  return { success: true, data }
}

function jwt(expInSeconds: number): string {
  const exp = Math.floor(Date.now() / 1000) + expInSeconds
  return `h.${btoa(JSON.stringify({ exp }))}.s`
}

const REFRESH = '/api/v1/method/grunt.auth.doctypes.User.user.refresh_api'

// Tests

describe('useAuthStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    accessToken.value = null
    localStorage.clear()
    sessionStorage.clear()
    mockPost.mockReset()
    mockGet.mockReset()
    mockPatch.mockReset()
  })

  describe('initial state', () => {
    it('is not logged in by default', () => {
      const auth = useAuthStore()
      expect(auth.isLoggedIn).toBe(false)
    })
  })

  describe('restore', () => {
    it('turns the session cookie into an access token and a profile', async () => {
      mockPost.mockResolvedValueOnce({ data: envelope(fakeTokenResponse) })
      const auth = useAuthStore()
      await auth.restore()
      expect(mockPost).toHaveBeenCalledWith(REFRESH)
      expect(auth.token).toBe('fake-access-token')
      expect(auth.user?.email).toBe('admin@grunt.local')
    })

    it('stays signed out without a session', async () => {
      mockPost.mockRejectedValueOnce({ response: { status: 401 } })
      const auth = useAuthStore()
      await auth.restore()
      expect(auth.isLoggedIn).toBe(false)
      expect(mockGet).not.toHaveBeenCalled()
    })

    it('offline, signs in with the cached profile', async () => {
      mockPost.mockRejectedValueOnce({ request: {} }) // no response: network down
      mockGet.mockResolvedValueOnce({ data: envelope(fakeUser) })
      const auth = useAuthStore()
      await auth.restore()
      expect(auth.token).toBeNull()
      expect(auth.user?.email).toBe('admin@grunt.local')
      expect(auth.isLoggedIn).toBe(true)
    })

    it("resumes this tab's impersonation", async () => {
      const token = jwt(600)
      sessionStorage.setItem('grunt_impersonation', JSON.stringify({
        token,
        by: { email: 'boss@grunt.local', full_name: 'Boss' },
      }))
      mockGet.mockResolvedValueOnce({ data: envelope({ ...fakeUser, email: 'member@grunt.local' }) })
      const auth = useAuthStore()
      await auth.restore()
      expect(mockPost).not.toHaveBeenCalled()
      expect(auth.token).toBe(token)
      expect(auth.isImpersonating).toBe(true)
      expect(auth.user?.email).toBe('member@grunt.local')
    })
  })

  describe('login', () => {
    it('sets token and user on success', async () => {
      mockPost.mockResolvedValueOnce({ data: envelope(fakeTokenResponse) })
      const auth = useAuthStore()
      await auth.login('admin@grunt.local', 'password')
      expect(auth.isLoggedIn).toBe(true)
      expect(auth.token).toBe('fake-access-token')
      expect(auth.user?.email).toBe('admin@grunt.local')
    })

    it('keeps no token in storage', async () => {
      mockPost.mockResolvedValueOnce({ data: envelope(fakeTokenResponse) })
      const auth = useAuthStore()
      await auth.login('admin@grunt.local', 'password')
      expect(localStorage.length).toBe(0)
      expect(sessionStorage.length).toBe(0)
    })

    it('posts the credentials', async () => {
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
    it('clears state', async () => {
      mockPost.mockResolvedValueOnce({ data: envelope(fakeTokenResponse) })
      const auth = useAuthStore()
      await auth.login('admin@grunt.local', 'password')
      mockPost.mockResolvedValueOnce({ data: { success: true } }) // logout endpoint
      await auth.logout()
      expect(auth.isLoggedIn).toBe(false)
      expect(auth.token).toBeNull()
      expect(auth.user).toBeNull()
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
    it('returns true and updates the token on success', async () => {
      mockPost.mockResolvedValueOnce({ data: envelope({ ...fakeTokenResponse, access_token: 'new-access' }) })
      const auth = useAuthStore()
      const ok = await auth.refresh()
      expect(ok).toBe(true)
      expect(mockPost).toHaveBeenCalledWith(REFRESH)
      expect(auth.token).toBe('new-access')
    })

    it('returns false and logs out on 401 response', async () => {
      accessToken.value = jwt(-60)
      mockPost.mockRejectedValueOnce({ response: { status: 401 } })
      const auth = useAuthStore()
      const ok = await auth.refresh()
      expect(ok).toBe(false)
      expect(auth.token).toBeNull()
    })

    it('keeps the session on a network error', async () => {
      const stale = jwt(-60)
      accessToken.value = stale
      mockPost.mockRejectedValueOnce({ request: {} })
      const auth = useAuthStore()
      expect(await auth.refresh()).toBe(false)
      expect(auth.token).toBe(stale)
    })

    it('does not renew an impersonation token', async () => {
      sessionStorage.setItem('grunt_impersonation', JSON.stringify({
        token: jwt(600),
        by: { email: 'boss@grunt.local', full_name: 'Boss' },
      }))
      mockGet.mockResolvedValueOnce({ data: envelope(fakeUser) })
      const auth = useAuthStore()
      await auth.restore()
      expect(await auth.refresh()).toBe(false)
      expect(mockPost).not.toHaveBeenCalled()
    })
  })

  describe('fetchMe', () => {
    it('populates user on success', async () => {
      accessToken.value = 'valid-token'
      mockGet.mockResolvedValueOnce({ data: fakeUser })
      const auth = useAuthStore()
      await auth.fetchMe()
      expect(auth.user?.email).toBe('admin@grunt.local')
    })

    it('logs out on 401', async () => {
      accessToken.value = 'bad-token'
      mockGet.mockRejectedValueOnce({ response: { status: 401 } })
      const auth = useAuthStore()
      await auth.fetchMe()
      expect(auth.isLoggedIn).toBe(false)
    })
  })
})
