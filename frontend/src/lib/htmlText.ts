/**
 * Plain text out of stored rich text (comments, RichText / HTMLEditor values)
 * for places that show it as text - never rendered as HTML.
 */

const HTML_TAG = /<\/?[a-z][^>]*>/i
// Closing block tags (and <br>) end a line; everything else is inline.
const BLOCK_END = /<(br|\/p|\/li|\/div|\/h[1-6]|\/tr|\/blockquote|\/pre)\b[^>]*>/gi

export function looksLikeHtml(value: string): boolean {
  return HTML_TAG.test(value)
}

/** Text with paragraphs / list items on their own lines (for `whitespace-pre-line`). */
export function htmlToText(html: string): string {
  if (!looksLikeHtml(html)) return html
  const marked = html.replace(BLOCK_END, '$&\n')
  const text = new DOMParser().parseFromString(marked, 'text/html').body.textContent ?? ''
  return text
    .split('\n')
    .map((line) => line.replace(/[ \t ]+/g, ' ').trim())
    .filter(Boolean)
    .join('\n')
}

/** Single-line text (blocks joined with spaces), e.g. for clamped previews. */
export function htmlToLine(html: string): string {
  return htmlToText(html).replace(/\n+/g, ' ')
}
