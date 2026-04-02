import client from './client'

export interface NotificationItem {
  id: string
  user: string
  subject: string
  message: string
  doctype?: string | null
  doc_id?: string | null
  is_read: boolean
  created_at: string
}

export const notificationsApi = {
  list: async (params?: { unread_only?: boolean; limit?: number; offset?: number }): Promise<NotificationItem[]> => {
    const res = await client.get('/api/v1/notifications', { params })
    return res.data.data
  },

  unreadCount: async (): Promise<number> => {
    const res = await client.get('/api/v1/notifications/unread-count')
    return res.data.count
  },

  markRead: async (id: string): Promise<void> => {
    await client.patch(`/api/v1/notifications/${id}/read`)
  },

  markAllRead: async (): Promise<number> => {
    const res = await client.post('/api/v1/notifications/read-all')
    return res.data.count
  }
}
