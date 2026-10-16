import { beforeEach, describe, expect, it } from 'vitest'
import { afterLoginTarget, loginLocation, rememberLoginRedirect } from '@/core/loginRedirect'

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
})
