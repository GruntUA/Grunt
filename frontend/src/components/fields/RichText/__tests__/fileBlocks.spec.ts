import { describe, expect, it } from 'vitest'
import { Editor } from '@tiptap/core'
import StarterKit from '@tiptap/starter-kit'
import Image from '@tiptap/extension-image'
import { FileList, Gallery, toFileEntry } from '../fileBlocks'

const URL = '/api/v1/method/grunt.storage.doctypes.File.file.get_content?file_id='

function roundTrip(html: string): Editor {
  return new Editor({
    extensions: [StarterKit, Image.configure({ inline: false }), FileList, Gallery],
    content: html,
  })
}

describe('RichText file blocks', () => {
  it('keeps a file list as a file-list <ul>, not a bullet list', () => {
    const html = `<ul class="file-list"><li><a href="${URL}a">Рішення.pdf</a> <span class="file-list__meta">PDF · 2 KB</span></li>`
      + `<li><a href="${URL}b">b.docx</a></li></ul><ul><li><p>plain</p></li></ul>`
    const editor = roundTrip(html)
    const json = editor.getJSON()
    expect(json.content?.map(n => n.type)).toEqual(['fileList', 'bulletList'])
    expect(json.content?.[0].attrs?.files).toEqual([
      { url: `${URL}a`, name: 'Рішення.pdf', meta: 'PDF · 2 KB' },
      { url: `${URL}b`, name: 'b.docx', meta: '' },
    ])
    expect(roundTrip(editor.getHTML()).getJSON()).toEqual(json)
  })

  it('parses the imported gallery markup and serializes it back', () => {
    const html = `<div class="gallery"><a class="gallery__item" href="${URL}f"><img src="${URL}f&amp;thumb=1" alt="Фото"></a></div>`
    const editor = roundTrip(html)
    expect(editor.getJSON().content?.[0]).toEqual({
      type: 'gallery',
      attrs: { images: [{ url: `${URL}f`, src: `${URL}f&thumb=1`, name: 'Фото' }] },
    })
    expect(editor.getHTML()).toBe(
      `<div class="gallery"><a class="gallery__item" href="${URL}f"><img src="${URL}f&amp;thumb=1" alt="Фото" loading="lazy"></a></div>`,
    )
  })

  it('describes a picked file by type and size', () => {
    expect(toFileEntry({
      url: `${URL}x`,
      filename: 'Звіт.pdf',
      contentType: 'application/pdf',
      fileItem: { size_bytes: 245760 } as never,
    })).toEqual({ url: `${URL}x`, name: 'Звіт.pdf', meta: 'PDF · 240 KB' })
  })
})
