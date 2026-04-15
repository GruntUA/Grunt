import client from './client'
import type { UserPublic } from '@/types'

export const authApi = {
  forgotPassword: (email: string): Promise<{ success: boolean }> =>
    client.post('/api/v1/auth/forgot-password', { email }).then(r => r.data),

  resetPassword: (token: string, newPassword: string): Promise<{ success: boolean }> =>
    client.post('/api/v1/auth/reset-password', { token, new_password: newPassword }).then(r => r.data),
}

export const authAdminApi = {
  listUsers: (): Promise<UserPublic[]> =>
    client.get('/api/v1/auth/users').then(r => r.data),

  listRoles: (): Promise<{ success: boolean; data: { name: string; description?: string }[] }> =>
    client.get('/api/v1/auth/roles').then(r => r.data),

  createRole: (roleName: string): Promise<{ success: boolean }> =>
    client.post('/api/v1/auth/roles', { role_name: roleName }).then(r => r.data),

  addRole: (userId: string, roleName: string): Promise<{ success: boolean }> =>
    client.post(`/api/v1/auth/users/${userId}/roles`, { role_name: roleName }).then(r => r.data),

  removeRole: (userId: string, role: string): Promise<{ success: boolean }> =>
    client.delete(`/api/v1/auth/users/${userId}/roles/${encodeURIComponent(role)}`).then(r => r.data),
}
