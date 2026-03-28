import client from './client'
import type { GruntNotification } from '@/types'

export const notificationsApi = {
  async list(params?: { unread_only?: boolean; limit?: number; offset?: number }) {
    const { data } = await client.get<{ success: boolean; data: GruntNotification[] }>(
      '/api/v1/notifications',
      { params },
    )
    return data.data
  },

  async unreadCount() {
    const { data } = await client.get<{ success: boolean; count: number }>(
      '/api/v1/notifications/unread-count',
    )
    return data.count
  },

  async markRead(notificationId: string) {
    await client.patch(`/api/v1/notifications/${notificationId}/read`)
  },

  async markAllRead() {
    const { data } = await client.post<{ success: boolean; count: number }>(
      '/api/v1/notifications/read-all',
    )
    return data.count
  },
}
