import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterLoginTarget, go, isSpaPath, loginLocation, rememberLoginRedirect } from '@/core/loginRedirect'

const Page = { template: '<div />' }

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/app', name: 'desk', component: Page },
      { path: '/app/:workspaceName', name: 'workspace-home', component: Page },
      { path: '/:workspaceName/:rest(.*)*', redirect: (to) => '/app' + to.fullPath },
      { path: '/:pathMatch(.*)*', name: 'not-found', component: Page },
    ],
  })
}

describe('loginRedirect', () => {
  beforeEach(() => sessionStorage.clear())

  it('carries the original path in the login query', () => {
    expect(loginLocation('/app/hr/Employee/E-1?tab=2')).toEqual({
      name: 'login',
      query: { redirect: '/app/hr/Employee/E-1?tab=2' },
    })
    expect(loginLocation('/')).toEqual({ name: 'login' })
    expect(loginLocation('/login?redirect=/x')).toEqual({ name: 'login' })
  })

  it('returns the stashed path once, then the desk', () => {
    rememberLoginRedirect('/app/hr/Employee')
    expect(afterLoginTarget()).toBe('/app/hr/Employee')
    expect(afterLoginTarget()).toEqual({ name: 'desk' })
  })

  it('ignores off-site and non-string targets', () => {
    for (const bad of ['//evil.com', '/\\evil.com', 'https://evil.com', ['/a'], undefined]) {
      rememberLoginRedirect(bad)
      expect(afterLoginTarget()).toEqual({ name: 'desk' })
    }
  })

  it('falls back to the home page, then the desk', () => {
    expect(afterLoginTarget('/app/hrm')).toBe('/app/hrm')
    rememberLoginRedirect('/app/hr/Employee')
    expect(afterLoginTarget('/app/hrm')).toBe('/app/hr/Employee')
    for (const bad of ['//evil.com', 'https://evil.com', '', null]) {
      expect(afterLoginTarget(bad)).toEqual({ name: 'desk' })
    }
  })

  it('tells SPA pages from website pages', () => {
    const router = makeRouter()
    expect(isSpaPath(router, '/app')).toBe(true)
    expect(isSpaPath(router, '/app/hrm')).toBe(true)
    expect(isSpaPath(router, '/cabinet')).toBe(false)
    expect(isSpaPath(router, '/')).toBe(false)
  })

  it('opens a website page with a full load', () => {
    const router = makeRouter()
    const push = vi.spyOn(router, 'push').mockResolvedValue(undefined)
    const assign = vi.fn()
    vi.stubGlobal('location', { ...window.location, assign })
    try {
      go(router, '/cabinet')
      expect(assign).toHaveBeenCalledWith('/cabinet')
      go(router, '/app/hrm')
      go(router, { name: 'desk' })
      expect(push).toHaveBeenCalledTimes(2)
    } finally {
      vi.unstubAllGlobals()
    }
  })
})
