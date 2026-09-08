/**
 * View helpers for File records — kept separate from the `core/api/files`
 * transport layer. Single home for the "is this an image?" / size-formatting /
 * file-id-from-URL logic that used to be copy-pasted across components.
 */

export function isImageType(contentType: string | null | undefined): boolean {
  return !!contentType && contentType.startsWith('image/')
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
