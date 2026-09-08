import type { Component } from 'vue'
import type { FileItem } from '@/core/api/files'

export interface AttachmentResult {
  url: string
  filename: string
  contentType?: string
  fileItem?: FileItem
}

export interface AttachChannel {
  id: string
  icon: Component
  label: string
  description?: string
  component: Component
  isSupported?: () => boolean
  /** Show this channel only when the picker is locked to images. */
  imageOnlyChannel?: boolean
}

/** Props every channel component receives from `AttachPicker`. */
export interface AttachChannelProps {
  imageOnly: boolean
  attachedToDoctype?: string
  attachedToId?: string
  multiple?: boolean
  currentUrl?: string | null
}

export interface AttachChannelEmits {
  (e: 'select', result: AttachmentResult): void
  (e: 'selectMany', results: AttachmentResult[]): void
}
