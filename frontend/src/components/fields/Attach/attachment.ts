import type { FileItem } from '@/core/api/files'

/** What the attach picker hands back: a file's URL and what to show for it. */
export interface AttachmentResult {
  url: string
  filename: string
  contentType?: string
  fileItem?: FileItem
}
