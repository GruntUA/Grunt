import { describe, expect, it } from 'vitest'

import { formPermissions, roleAllows } from '@/core/permissions'
import type { DocType } from '@/types'

const dt = {
  name: 'Box',
  permissions: [
    { role: 'System Manager', read: true, write: true, create: true, delete: true },
    { role: 'Reader', read: true },
    { role: 'All', read: true, create: true },
  ],
} as unknown as DocType

describe('roleAllows', () => {
  it('matches the user roles and All', () => {
    expect(roleAllows(dt, 'write', ['Reader'])).toBe(false)
    expect(roleAllows(dt, 'write', ['System Manager'])).toBe(true)
    expect(roleAllows(dt, 'create', [])).toBe(true) // via All
  })

  it('closes a DocType without permission rows to everyone', () => {
    expect(roleAllows({ name: 'X', permissions: [] } as unknown as DocType, 'create', ['System Manager'])).toBe(false)
  })
})

describe('formPermissions', () => {
  it("trusts the server's __perms for an existing document", () => {
    const doc = { name: 'a', __perms: { write: false, delete: false, create: true } }
    expect(formPermissions(dt, doc, false, ['System Manager'])).toEqual({ write: false, delete: false, create: true })
  })

  it('uses the create right for a new document', () => {
    expect(formPermissions(dt, null, true, ['Reader'])).toEqual({ write: true, delete: false, create: true })
    const closed = { name: 'Y', permissions: [{ role: 'Reader', read: true }] } as unknown as DocType
    expect(formPermissions(closed, null, true, ['Reader']).write).toBe(false)
  })

  it('falls back to role rows when the document has no __perms (e.g. an offline copy)', () => {
    expect(formPermissions(dt, { name: 'a' }, false, ['Reader'])).toEqual({ write: false, delete: false, create: true })
  })
})
