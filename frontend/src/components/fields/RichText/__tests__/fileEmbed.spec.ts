import { describe, expect, it } from 'vitest'
import { Editor } from '@tiptap/core'
import StarterKit from '@tiptap/starter-kit'
import { FileList } from '../extensions/fileBlocks'
import { FileEmbed, OFFICE_VIEWER, canEmbed, embedSrc } from '../extensions/fileEmbed'

const URL = '/api/v1/method/grunt.storage.doctypes.File.file.get_content?file_id='
const ORIGIN = window.location.origin

function roundTrip(html: string): Editor {
  return new Editor({ extensions: [StarterKit, FileList, FileEmbed], content: html })
}

describe('RichText file embed', () => {
  it('shows a PDF from the site and an Office file through the Office viewer', () => {
    expect(embedSrc(`${URL}abc`, 'Рішення.PDF')).toBe('/api/v1/files/abc.pdf')
    expect(embedSrc(`${URL}abc&exp=1&sig=ff`, 'Звіт.xlsx', 'https://mlt.example'))
      .toBe(`${OFFICE_VIEWER}${encodeURIComponent('https://mlt.example/api/v1/files/abc.xlsx')}`)
    expect(embedSrc(`${URL}abc`, 'photo.jpg')).toBeNull()
    expect(embedSrc('https://elsewhere.example/a.pdf', 'a.pdf')).toBeNull()
  })

  it('knows which files can be shown', () => {
    expect(['a.pdf', 'b.docx', 'c.doc', 'd.XLSX', 'e.xls', 'f.pptx', 'g.ppt'].every(canEmbed)).toBe(true)
    expect(['a.jpg', 'b.zip', 'noext', 'c.odt'].some(canEmbed)).toBe(false)
  })

  it('stores a figure with the frame and a download link, and parses it back', () => {
    const editor = roundTrip('<p>x</p>')
    editor.commands.insertContent({ type: 'fileEmbed', attrs: { url: `${URL}d1`, name: 'План.docx', meta: 'DOCX · 12 KB' } })
    const html = editor.getHTML()
    const src = `${OFFICE_VIEWER}${encodeURIComponent(`${ORIGIN}/api/v1/files/d1.docx`)}`
    expect(html).toContain(
      `<figure class="file-embed"><iframe src="${src}" title="План.docx" loading="lazy" allowfullscreen="true" width="100%" height="720"></iframe>`
      + `<figcaption><a href="${URL}d1">План.docx</a> <span class="file-embed__meta">DOCX · 12 KB</span></figcaption></figure>`,
    )
    const json = editor.getJSON()
    expect(json.content?.find(n => n.type === 'fileEmbed')?.attrs).toEqual({ url: `${URL}d1`, name: 'План.docx', meta: 'DOCX · 12 KB' })
    expect(roundTrip(html).getJSON()).toEqual(json)
  })

  it('takes the file from the caption link, whatever the frame says', () => {
    const editor = roundTrip(
      `<figure class="file-embed"><iframe src="/api/v1/files/old.pdf"></iframe>`
      + `<figcaption><a href="${URL}new">Новий.pdf</a></figcaption></figure>`,
    )
    expect(editor.getHTML()).toBe(
      `<figure class="file-embed"><iframe src="/api/v1/files/new.pdf" title="Новий.pdf" loading="lazy" allowfullscreen="true" width="100%" height="720"></iframe>`
      + `<figcaption><a href="${URL}new">Новий.pdf</a></figcaption></figure>`,
    )
  })
})
