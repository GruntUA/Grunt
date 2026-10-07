import client from './client'

export interface NotificationItem {
  id: string
  user: string
  subject: string
  message: string
  ref_doctype?: string | null
  doc_id?: string | null
  is_read: boolean
  created_at: string
}

export const notificationsApi = {
  list: async (params?: { unread_only?: boolean; limit?: number; offset?: number }): Promise<NotificationItem[]> => {
    // Map offset/limit to page/per_page
    const limit = params?.limit || 20
    const offset = params?.offset || 0
    const page = Math.floor(offset / limit) + 1

    const queryParams: Record<string, any> = { page, per_page: limit }
    if (params?.unread_only !== undefined) {
      queryParams.unread_only = params.unread_only
    }

    const res = await client.get('/api/v1/method/grunt.api.v1.notifications.list_notifications', { params: queryParams })
    return res.data.data.items
  },

  unreadCount: async (): Promise<number> => {
    const res = await client.get('/api/v1/method/grunt.api.v1.notifications.get_unread_count')
    return res.data.data
  },

  markRead: async (id: string): Promise<void> => {
    await client.post('/api/v1/method/grunt.api.v1.notifications.mark_as_read', { notification_id: id })
  },

  markAllRead: async (): Promise<number> => {
    const res = await client.post('/api/v1/method/grunt.api.v1.notifications.mark_all_as_read')
    return res.data.data.count
  }
}
