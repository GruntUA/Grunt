/** Notifications and realtime events. */

export interface GruntNotification {
  id: string
  subject: string
  message: string
  ref_doctype?: string | null
  doc_id?: string | null
  is_read: boolean
  created_at: string | null
}

export type RealtimeMessageType = 'success' | 'error' | 'info' | 'warning'

export interface RealtimeEvent {
  event: string
  data: {
    message?: string
    type?: RealtimeMessageType
    subject?: string
    doctype?: string
    ref_doctype?: string
    doc_id?: string
    [key: string]: unknown
  }
}
