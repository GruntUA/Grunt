import { describe, expect, it } from 'vitest'
import { Editor } from '@tiptap/core'
import StarterKit from '@tiptap/starter-kit'
import { YoutubeEmbed, canonicalUrl } from '../extensions/youtube'

const ID = 'spQHbqNN28A'
const WATCH = `https://www.youtube.com/watch?v=${ID}`
const EMBED = `https://www.youtube-nocookie.com/embed/${ID}`

function editor(content = '<p>x</p>'): Editor {
  return new Editor({ extensions: [StarterKit, YoutubeEmbed], content })
}

describe('RichText YouTube embed', () => {
  it('reduces any video link to a watch URL', () => {
    for (const url of [
      `${WATCH}&feature=youtu.be`,
      `https://youtu.be/${ID}?si=abc`,
      `https://m.youtube.com/shorts/${ID}`,
      `${EMBED}?rel=0`,
      `https://www.youtube-nocookie.com/embed/watch?v=${ID}&feature=youtu.be`,
    ]) expect(canonicalUrl(url), url).toBe(WATCH)
    expect(canonicalUrl('https://www.youtube.com/playlist?list=PL1')).toBe('https://www.youtube.com/playlist?list=PL1')
  })

  it('embeds a watch link that mentions youtu.be by its id', () => {
    const e = editor()
    expect(e.commands.setYoutubeVideo({ src: `${WATCH}&feature=youtu.be` })).toBe(true)
    expect(e.getHTML()).toContain(`src="${EMBED}?rel=1"`)
  })

  it('repairs an iframe saved with the broken embed/watch src', () => {
    const html = editor(`<iframe src="https://www.youtube-nocookie.com/embed/watch?v=${ID}&amp;feature=youtu.be"></iframe>`).getHTML()
    expect(html).toContain(`src="${EMBED}?rel=1"`)
  })
})
