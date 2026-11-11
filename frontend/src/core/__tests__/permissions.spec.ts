import { describe, expect, it } from 'vitest'

import { formPermissions, formReadonlyFields, NO_PERMS, roleAllows, rolePermissions } from '@/core/permissions'
import type { DocType } from '@/types'

const dt = {
  name: 'Box',
  permissions: [
    { role: 'System Manager', actions: ['read', 'write', 'create', 'delete', 'export', 'share'] },
    { role: 'Reader', actions: ['read', 'print'] },
    { role: 'Lender', actions: ['read', 'share'] },
    { role: 'All', actions: ['read', 'create'] },
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

  it('grants export / print only where a row lists them', () => {
    expect(roleAllows(dt, 'export', ['Reader'])).toBe(false)
    expect(roleAllows(dt, 'print', ['Reader'])).toBe(true)
    expect(roleAllows(dt, 'export', ['System Manager'])).toBe(true)
  })

  it('needs write besides share', () => {
    expect(roleAllows(dt, 'share', ['Lender'])).toBe(false)
    expect(roleAllows(dt, 'share', ['System Manager'])).toBe(true)
  })
})

describe('formPermissions', () => {
  const server = { write: false, delete: false, create: true, print: true, share: false }

  it("trusts the server's __perms for an existing document", () => {
    const doc = { name: 'a', __perms: server }
    expect(formPermissions(dt, doc, false, ['System Manager'])).toEqual({
      ...server,
      // DocType-level - from the role rows
      export: true,
      import: false,
      report: false,
    })
  })

  it('uses the create right for a new document - not printable or shareable yet', () => {
    expect(formPermissions(dt, null, true, ['Reader'])).toEqual({ ...NO_PERMS, write: true, create: true })
    const closed = { name: 'Y', permissions: [{ role: 'Reader', actions: ['read'] }] } as unknown as DocType
    expect(formPermissions(closed, null, true, ['Reader']).write).toBe(false)
  })

  it('falls back to role rows when the document has no __perms (e.g. an offline copy)', () => {
    expect(formPermissions(dt, { name: 'a' }, false, ['Reader'])).toEqual(rolePermissions(dt, ['Reader']))
    expect(rolePermissions(dt, ['Reader'])).toEqual({ ...NO_PERMS, create: true, print: true })
  })
})

describe('formReadonlyFields', () => {
  const card = {
    name: 'Card',
    permissions: [
      { role: 'Accountant', actions: ['read', 'write'], readonly_fields: ['salary', 'bonus'] },
      { role: 'Clerk', actions: ['read', 'write'], readonly_fields: ['salary'], hidden_fields: ['bonus'] },
      { role: 'HR', actions: ['read', 'write'] },
      { role: 'Viewer', actions: ['read'], readonly_fields: ['note'] },
    ],
  } as unknown as DocType

  it("trusts the server's __perms", () => {
    expect(formReadonlyFields(card, { __perms: { readonly_fields: ['x'] } }, false, ['HR'])).toEqual(['x'])
  })

  it('locks a field only when every write rule does', () => {
    expect(formReadonlyFields(card, {}, false, ['Accountant']).sort()).toEqual(['bonus', 'salary'])
    expect(formReadonlyFields(card, {}, false, ['Accountant', 'Clerk']).sort()).toEqual(['bonus', 'salary'])
    expect(formReadonlyFields(card, {}, false, ['Accountant', 'HR'])).toEqual([])
    expect(formReadonlyFields(card, {}, false, ['Viewer'])).toEqual([]) // no write rule
  })

  it('leaves a new document editable', () => {
    expect(formReadonlyFields(card, null, true, ['Accountant'])).toEqual([])
  })
})

