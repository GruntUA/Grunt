/**
 * What the current user may do - so the UI hides actions the server would
 * refuse (instead of letting the user edit and then answering 403).
 *
 * An existing document carries its own answer: the API adds `__perms`
 * (grunt/permissions/doc_perms.py - roles, row-level `match`, User
 * Permissions, shares). Without a document (a new one, the list's «Add»)
 * only the role rows can be mirrored here.
 */
import type { DocType, PermissionAction } from '@/types'

/** Per-document answers: the server's `__perms` (create is DocType-level there too). */
export type DocAction = 'write' | 'delete' | 'create' | 'print' | 'share'
/** DocType-level only - taken from the role rows. */
export type DocTypeAction = 'export' | 'import' | 'report'
export type DocPerms = Record<DocAction | DocTypeAction, boolean>

const DOC_ACTIONS: DocAction[] = ['write', 'delete', 'create', 'print', 'share']
const DOCTYPE_ACTIONS: DocTypeAction[] = ['export', 'import', 'report']

export const PERMS_KEY = '__perms'

/** Nothing allowed - the default before anything is known. */
export const NO_PERMS: DocPerms = {
  write: false,
  delete: false,
  create: false,
  print: false,
  share: false,
  export: false,
  import: false,
  report: false,
}

/**
 * Role-level check, as the backend's RoleAccess does it: a DocType with no
 * permission rows is closed to everyone; `All` matches every user. Ignores
 * row-level `match` and shares - those need the document (see `__perms`).
 */
export function roleAllows(
  dt: DocType | null | undefined,
  action: DocAction | DocTypeAction,
  roles: string[],
): boolean {
  const perms = dt?.permissions
  if (!perms?.length) return false
  const granted = (a: PermissionAction) =>
    perms.some((p) => p.actions?.includes(a) && (p.role === 'All' || roles.includes(p.role)))
  // Sharing never hands out more than the sharer may do: share needs write too.
  return action === 'share' ? granted('share') && granted('write') : granted(action)
}

/** Every action by the role rows alone - a list, or a document not loaded yet. */
export function rolePermissions(dt: DocType | null | undefined, roles: string[]): DocPerms {
  return Object.fromEntries(
    [...DOC_ACTIONS, ...DOCTYPE_ACTIONS].map((a) => [a, roleAllows(dt, a, roles)]),
  ) as DocPerms
}

/** Permissions for the form: the server's `__perms`, or the role rows for a new document. */
export function formPermissions(
  dt: DocType | null | undefined,
  doc: Record<string, unknown> | null | undefined,
  isNew: boolean,
  roles: string[],
): DocPerms {
  // meta loading - no flash of read-only
  if (!dt) return { ...NO_PERMS, write: true }
  const byRole = rolePermissions(dt, roles)
  // A new document can't be printed or shared before it is saved.
  if (isNew) return { ...byRole, write: byRole.create, delete: false, print: false, share: false }
  const server = doc?.[PERMS_KEY] as Partial<Record<DocAction, boolean>> | undefined
  if (!server) return byRole
  const perms = { ...byRole }
  for (const a of DOC_ACTIONS) perms[a] = !!server[a]
  return perms
}

/**
 * Fields the form shows but doesn't let the user change: the server's
 * `__perms.readonly_fields`, or - without it - those every role row granting
 * write lists as read-only (or hidden). A new document takes their value.
 */
export function formReadonlyFields(
  dt: DocType | null | undefined,
  doc: Record<string, unknown> | null | undefined,
  isNew: boolean,
  roles: string[],
): string[] {
  if (!dt || isNew) return []
  const server = (doc?.[PERMS_KEY] as { readonly_fields?: string[] } | undefined)?.readonly_fields
  if (server) return server
  let locked = null as Set<string> | null
  for (const p of dt.permissions ?? []) {
    if (!p.actions?.includes('write') || (p.role !== 'All' && !roles.includes(p.role))) continue
    const rule = new Set([...(p.readonly_fields ?? []), ...(p.hidden_fields ?? [])])
    locked = locked ? new Set([...locked].filter((f) => rule.has(f))) : rule
  }
  return [...(locked ?? [])]
}
