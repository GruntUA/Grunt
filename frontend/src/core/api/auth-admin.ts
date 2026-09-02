import client from './client'
import type { UserPublic } from '@/types'

export const authApi = {
  forgotPassword: (email: string): Promise<{ success: boolean }> =>
    client.post('/api/v1/method/grunt.auth.doctypes.User.user.forgot_password_api', { email }).then(r => r.data),

  resetPassword: (token: string, newPassword: string): Promise<{ success: boolean }> =>
    client.post('/api/v1/method/grunt.auth.doctypes.User.user.reset_password_api', { token, new_password: newPassword }).then(r => r.data),
}

export const authAdminApi = {
  listUsers: (): Promise<UserPublic[]> =>
    client.get('/api/v1/method/grunt.auth.doctypes.User.user.list_users_detailed_api').then(r => r.data.data),

  listRoles: (): Promise<{ success: boolean; data: { name: string; description?: string }[] }> =>
    client.get('/api/v1/method/grunt.auth.doctypes.User.user.list_roles_api').then(r => r.data),

  createRole: (roleName: string): Promise<{ success: boolean }> =>
    client.post('/api/v1/method/grunt.auth.doctypes.User.user.create_role_api', { role_name: roleName }).then(r => r.data),

  addRole: (userId: string, roleName: string): Promise<{ success: boolean }> =>
    client.post('/api/v1/method/grunt.auth.doctypes.User.user.add_role', { user_id: userId, role_name: roleName }).then(r => r.data),

  removeRole: (userId: string, role: string): Promise<{ success: boolean }> =>
    client.post('/api/v1/method/grunt.auth.doctypes.User.user.remove_role', { user_id: userId, role_name: role }).then(r => r.data),

  /** Superadmin: open a short-lived session as another user. */
  startImpersonation: (userId: string): Promise<{
    access_token: string
    expires_in_minutes: number
    user: UserPublic
    impersonated_by: { id: string; email: string; full_name: string }
  }> =>
    client.post('/api/v1/method/grunt.auth.doctypes.User.user.start_impersonation_api', { user_id: userId }).then(r => r.data.data),

  stopImpersonation: (): Promise<{ success: boolean }> =>
    client.post('/api/v1/method/grunt.auth.doctypes.User.user.stop_impersonation_api').then(r => r.data),
}
