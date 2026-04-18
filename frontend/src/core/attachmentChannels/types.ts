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
  acceptsImageOnly?: boolean
}
