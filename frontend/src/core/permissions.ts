/**
 * What the current user may do — so the UI hides actions the server would
 * refuse (instead of letting the user edit and then answering 403).
 *
 * An existing document carries its own answer: the API adds `__perms`
 * (grunt/permissions/doc_perms.py — roles, row-level `match`, User
 * Permissions, shares). Without a document (a new one, the list's «Add»)
 * only the role rows can be mirrored here.
 */
import type { DocType } from '@/types'

export type DocAction = 'write' | 'delete' | 'create'
export type DocPerms = Record<DocAction, boolean>

export const PERMS_KEY = '__perms'

/**
 * Role-level check, as the backend's RoleAccess does it: a DocType with no
 * permission rows is closed to everyone; `All` matches every user. Ignores
 * row-level `match` and shares — those need the document (see `__perms`).
 */
export function roleAllows(dt: DocType | null | undefined, action: DocAction, roles: string[]): boolean {
  const perms = dt?.permissions
  if (!perms?.length) return false
  return perms.some((p) => p[action] && (p.role === 'All' || roles.includes(p.role)))
}

/** Permissions for the form: the server's `__perms`, or the role rows for a new document. */
export function formPermissions(
  dt: DocType | null | undefined,
  doc: Record<string, unknown> | null | undefined,
  isNew: boolean,
  roles: string[],
): DocPerms {
  if (!dt) return { write: true, delete: false, create: false } // meta loading — no flash of read-only
  const create = roleAllows(dt, 'create', roles)
  if (isNew) return { write: create, delete: false, create }
  const server = doc?.[PERMS_KEY] as Partial<DocPerms> | undefined
  if (server) return { write: !!server.write, delete: !!server.delete, create: !!server.create }
  return { write: roleAllows(dt, 'write', roles), delete: roleAllows(dt, 'delete', roles), create }
}
