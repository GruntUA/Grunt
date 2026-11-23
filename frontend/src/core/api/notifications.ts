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
  /** The rule that sent it - empty for a notification sent from code. */
  notification?: string | null
}

export interface NotificationPreferences {
  channels: { value: string; label: string }[]
  rules: { name: string; label: string; ref_doctype: string | null; channels: string[]; mandatory: boolean }[]
  /** What is off: `notification` null - all notifications, `channel` null - every channel. */
  off: { notification: string | null; channel: string | null }[]
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
  },

  preferences: async (): Promise<NotificationPreferences> => {
    const res = await client.get('/api/v1/method/grunt.api.v1.notifications.get_preferences')
    return res.data.data
  },

  setPreference: async (channel: string, enabled: boolean, notification?: string | null): Promise<NotificationPreferences> => {
    const res = await client.post('/api/v1/method/grunt.api.v1.notifications.set_preference', {
      channel, enabled, notification: notification ?? '',
    })
    return res.data.data
  },

  /** The bell's "Don't send these": turns the item's rule off in every channel. */
  muteLike: async (id: string): Promise<string> => {
    const res = await client.post('/api/v1/method/grunt.api.v1.notifications.mute_like', { notification_id: id })
    return res.data.data
  },
}
