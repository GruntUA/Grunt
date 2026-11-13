import client from './client'
import type { PermissionAction } from '@/types'

export interface ActiveRestriction {
  field: string
  fieldname: string
  allow: string
  value: string
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

  /** Row-level User Permission restrictions that apply to the current user on `doctype`. */
  getRestrictions: async (doctype: string): Promise<ActiveRestriction[]> => {
    const r = await client.get(
      '/api/v1/method/grunt.permissions.user_permissions.get_active_restrictions',
      { params: { doctype } },
    )
    return r.data.data ?? []
  },

  /** `{fieldname: value}` to pre-fill on a new `doctype` form from is_default User Permissions. */
  getUserPermissionDefaults: async (doctype: string): Promise<Record<string, string>> => {
    const r = await client.get(
      '/api/v1/method/grunt.permissions.user_permissions.get_user_permission_defaults',
      { params: { doctype } },
    )
    return r.data.data ?? {}
  },
}
