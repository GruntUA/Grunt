import { nodePasteRule } from '@tiptap/core'
import Youtube from '@tiptap/extension-youtube'

const ID = /^[\w-]{11}$/

/**
 * Any YouTube link (watch, youtu.be, shorts, live, embed) as a plain watch URL,
 * or the input unchanged when no video id is found (playlists etc.).
 *
 * The extension treats every URL containing "youtu.be" as a short link and takes
 * whatever follows the last "/" as the id, so `watch?v=X&feature=youtu.be` became
 * `embed/watch?v=X&feature=youtu.be`; and an embed src like that parses back as
 * id "watch". Feeding it a canonical URL avoids both.
 */
export function canonicalUrl(url: string): string {
  let u: URL
  try {
    u = new URL(url.trim().replace(/^\/\//, 'https://'))
  } catch {
    return url
  }
  const host = u.hostname.replace(/^(www|m|music)\./, '')
  let id: string | null = null
  if (host === 'youtu.be') {
    id = u.pathname.split('/')[1] ?? null
  } else if (host === 'youtube.com' || host === 'youtube-nocookie.com') {
    // `v=` first: the broken `/embed/watch?v=X` src must yield X, not "watch".
    id = u.searchParams.get('v') ?? u.pathname.match(/^\/(?:embed|shorts|live|v)\/([\w-]+)/)?.[1] ?? null
  }
  return id && ID.test(id) ? `https://www.youtube.com/watch?v=${id}` : url
}

// The sanitizer (grunt/utils/sanitize.py) keeps the iframe but strips the
// extension's `data-youtube-video` wrapper marker, so saved and imported
// content is recognised by the embed src instead.
export const YoutubeEmbed = Youtube.extend({
  parseHTML() {
    return [
      { tag: 'iframe[src*="youtube.com/embed/"]' },
      { tag: 'iframe[src*="youtube-nocookie.com/embed/"]' },
    ]
  },
  addAttributes() {
    return {
      ...this.parent?.(),
      src: { default: null, parseHTML: el => canonicalUrl(el.getAttribute('src') ?? '') || null },
    }
  },
  addCommands() {
    const parent = this.parent?.()
    return {
      setYoutubeVideo: options => props => parent!.setYoutubeVideo!({ ...options, src: canonicalUrl(options.src) })(props),
    }
  },
  addPasteRules() {
    if (!this.options.addPasteHandler) return []
    return [nodePasteRule({
      find: /^(?:https?:)?\/\/(?:(?:www|m|music)\.)?(?:youtube\.com|youtu\.be|youtube-nocookie\.com)\/\S+$/g,
      type: this.type,
      getAttributes: match => ({ src: canonicalUrl(match.input ?? '') }),
    })]
  },
}).configure({
  nocookie: true,
  width: 640,
  height: 360,
  // YouTube refuses to play without a Referer (error 153); the element
  // attribute overrides a stricter page policy (e.g. a proxy's same-origin).
  HTMLAttributes: { referrerpolicy: 'strict-origin-when-cross-origin' },
})

/** Embed src of the selected video as a regular watch URL (for editing). */
export function watchUrl(src: string): string {
  return canonicalUrl(src)
}
