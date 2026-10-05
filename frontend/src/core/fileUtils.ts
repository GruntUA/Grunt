/**
 * View helpers for File records - kept separate from the `core/api/files`
 * transport layer. Single home for the "is this an image?" / size-formatting /
 * file-id-from-URL logic that used to be copy-pasted across components.
 */

export function isImageType(contentType: string | null | undefined): boolean {
  return !!contentType && contentType.startsWith('image/')
}

/** What a grid tile shows: the server preview, else the image itself, else nothing (icon). */
export function previewUrl(file: {
  url: string
  content_type?: string | null
  thumbnail_url?: string | null
}): string | null {
  return file.thumbnail_url || (isImageType(file.content_type) ? file.url : null)
}

/** Short type tag for a tile: the file extension ("DOCX"), else the MIME subtype. */
export function fileTypeLabel(filename: string, contentType?: string | null): string {
  const ext = /\.([a-z0-9]{1,5})$/i.exec(filename)?.[1]
  return (ext || contentType?.split('/')[1] || 'file').toUpperCase()
}

const SIZE_UNITS = ['B', 'KB', 'MB', 'GB', 'TB'] as const

export function formatFileSize(bytes: number): string {
  if (!bytes || bytes < 0) return '0 B'
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), SIZE_UNITS.length - 1)
  const n = bytes / 1024 ** i
  return `${i === 0 ? Math.round(n) : n.toFixed(n < 10 ? 1 : 0)} ${SIZE_UNITS[i]}`
}

/** Pull the `file_id` query param out of a stored file URL, if present. */
export function extractFileId(url: string): string | null {
  try {
    return new URL(url, window.location.origin).searchParams.get('file_id')
  } catch {
    const m = url.match(/[?&]file_id=([^&]+)/)
    return m ? decodeURIComponent(m[1]) : null
  }
}
