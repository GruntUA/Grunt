import client from './client'

export interface ActiveRestriction {
  field: string
  fieldname: string
  allow: string
  value: string
}

export const permissionsApi = {
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
