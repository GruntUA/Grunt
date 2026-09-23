import { describe, expect, it } from 'vitest'
import { parseDocUrl } from '../useOfflineQueue'

describe('offline queue scope', () => {
  it('queues document create / update / delete only', () => {
    expect(parseDocUrl('post', '/api/v1/docs/ToDo')).toEqual({ doctype: 'ToDo', docId: null })
    expect(parseDocUrl('put', '/api/v1/docs/ToDo/abc')).toEqual({ doctype: 'ToDo', docId: 'abc' })
    expect(parseDocUrl('DELETE', '/api/v1/docs/%D0%90%D0%BA%D1%82/x%2Fy')).toEqual({ doctype: 'Акт', docId: 'x/y' })
  })

  it('never queues actions, RPCs or login', () => {
    expect(parseDocUrl('post', '/api/v1/docs/ToDo/abc')).toBeNull() // POST on a document = an action
    expect(parseDocUrl('post', '/api/v1/method/grunt.auth.doctypes.User.user.login_api')).toBeNull()
    expect(parseDocUrl('put', '/api/v1/docs/ToDo')).toBeNull()
    expect(parseDocUrl('post', '/api/v1/auth/webauthn/complete')).toBeNull()
  })
})
