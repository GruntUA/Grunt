import client from './client'
import type { Colleague, UserPublic } from '@/types'

export const authApi = {
  /** Active users - for share / assign / @mention pickers (any signed-in user). */
  listColleagues: (): Promise<Colleague[]> =>
    client.get('/api/v1/method/grunt.auth.user_api.list_colleagues_api').then(r => r.data.data),

  forgotPassword: (email: string): Promise<{ success: boolean }> =>
    client.post('/api/v1/method/grunt.auth.user_api.forgot_password_api', { email }).then(r => r.data),

  resetPassword: (token: string, newPassword: string): Promise<{ success: boolean }> =>
    client.post('/api/v1/method/grunt.auth.user_api.reset_password_api', { token, new_password: newPassword }).then(r => r.data),
}

export const authAdminApi = {
  listUsers: (): Promise<UserPublic[]> =>
    client.get('/api/v1/method/grunt.auth.user_api.list_users_detailed_api').then(r => r.data.data),

  /** System Manager: open a short-lived session as another user. */
  startImpersonation: (userId: string): Promise<{
    access_token: string
    expires_in_minutes: number
    user: UserPublic
    impersonated_by: { id: string; email: string; full_name: string }
  }> =>
    client.post('/api/v1/method/grunt.auth.user_api.start_impersonation_api', { user_id: userId }).then(r => r.data.data),

  stopImpersonation: (): Promise<{ success: boolean }> =>
    client.post('/api/v1/method/grunt.auth.user_api.stop_impersonation_api').then(r => r.data),
}
