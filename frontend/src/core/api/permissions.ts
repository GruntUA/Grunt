import client from './client'
import type { PermissionAction } from '@/types'

/** A scope of the user's role that limits a list (grunt.permissions.scopes). */
export interface ActiveRestriction {
  field: string
  fieldname: string
  allow: string
  value: string
  /** The scope record's title (its id when it has none). */
  title: string
}

/** One rule of the DocType in an access trace (grunt.permissions.explain). */
export interface AccessRule {
  index: number
  role: string
  /** The user holds the role (or it is "All"). */
  held: boolean
  grants: boolean
  match: string | null
  scopes: { doctype: string; values: string[] }[]
  unparseable: boolean
  /** Whether the document passes the rule's match and scope; null - not checked. */
  doc_ok: boolean | null
}

/** Why a user may (or may not) do something (grunt.api.v1.permission_inspector). */
export interface AccessTrace {
  user: string
  user_name: string
  doctype: string
  action: string
  doc: string | null
  allowed: boolean
  roles: { role: string; scope_doctype: string | null; scope_value: string | null; valid_to: string | null }[]
  child: boolean
  rules: AccessRule[]
  role_grants: boolean
  /** False - the document follows the access of the documents in `followed`. */
  rules_decide: boolean
  shares: { name: string; via: 'user' | 'role' | 'everyone'; role: string | null; permission: string; can_reshare: boolean; valid_to: string | null }[]
  followed: { field: string; doctype: string; name: string; allowed: boolean }[]
  hidden_fields: string[]
  readonly_fields: string[]
  /** `"<DocType>/<id>"` -> title of the scope records named above. */
  titles: Record<string, string>
}

/** One rule of a role on a DocType (grunt.api.v1.permission_matrix). */
export interface MatrixRule {
  /** Position in the DocType's `permissions`. */
  index: number
  actions: PermissionAction[]
  match: string | null
  hidden_fields: string[]
  readonly_fields: string[]
}

export interface MatrixRow {
  doctype: string
  is_child: boolean
  rules: MatrixRule[]
}

/** A changed rule: `index` null adds one (without a condition). */
export interface MatrixEdit {
  index: number | null
  match?: string | null
  /** The rule's actions as loaded - a save over changed ones is refused. */
  original?: PermissionAction[]
  actions: PermissionAction[]
}

const MATRIX = '/api/v1/method/grunt.api.v1.permission_matrix'

export const permissionsApi = {
  /** `role`'s rules on each of `doctypes`. */
  getRoleMatrix: async (role: string, doctypes: string[]): Promise<MatrixRow[]> => {
    const r = await client.post(`${MATRIX}.get_role_matrix`, { role, doctypes })
    return r.data.data ?? []
  },

  /** Save `role`'s changed rules, one DocType at a time; returns them re-read. */
  saveRoleMatrix: async (
    role: string,
    changes: { doctype: string; rules: MatrixEdit[] }[],
  ): Promise<MatrixRow[]> => {
    const r = await client.post(`${MATRIX}.save_role_matrix`, { role, changes })
    return r.data.data ?? []
  },

  /** Why `user` may (or may not) perform `action` on `doctype` (or its document `name`). */
  explainAccess: async (user: string, doctype: string, action: string, name?: string | null): Promise<AccessTrace> => {
    const r = await client.get('/api/v1/method/grunt.api.v1.permission_inspector.explain_access', {
      params: { user, doctype, action, ...(name ? { name } : {}) },
    })
    return r.data.data
  },

  /** Scopes of the current user's roles that limit a `doctype` list. */
  getRestrictions: async (doctype: string): Promise<ActiveRestriction[]> => {
    const r = await client.get('/api/v1/method/grunt.api.v1.role_scopes.get_active_scopes', {
      params: { doctype },
    })
    return r.data.data ?? []
  },

  /** `{fieldname: value}` to pre-fill on a new `doctype` form: the one scope record the user creates within. */
  getScopeDefaults: async (doctype: string): Promise<Record<string, string>> => {
    const r = await client.get('/api/v1/method/grunt.api.v1.role_scopes.get_scope_defaults', {
      params: { doctype },
    })
    return r.data.data ?? {}
  },
}
