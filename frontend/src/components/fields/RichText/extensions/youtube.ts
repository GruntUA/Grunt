import Youtube from '@tiptap/extension-youtube'

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
  const id = src.match(/\/embed\/([\w-]+)/)?.[1]
  return id ? `https://www.youtube.com/watch?v=${id}` : src
}
