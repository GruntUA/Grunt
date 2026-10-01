import { describe, expect, it } from 'vitest'
import { Editor } from '@tiptap/core'
import StarterKit from '@tiptap/starter-kit'
import { TableKit } from '@tiptap/extension-table'
import { RichTableCell, RichTableHeader, applyDocxTableLayout } from '../tableCells'

function editorWith(html: string): Editor {
  return new Editor({
    extensions: [
      StarterKit,
      TableKit.configure({ tableCell: false, tableHeader: false }),
      RichTableCell,
      RichTableHeader,
    ],
    content: html,
  })
}

const cellAttrs = (editor: Editor) => {
  const out: Record<string, unknown>[] = []
  editor.state.doc.descendants((n) => { if (n.type.name === 'tableCell') out.push(n.attrs) })
  return out
}

const W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
// 3 columns (30 / 120 / 60 px); the third column is one vertical, merged cell.
const DOCUMENT_XML = `<w:document ${W}><w:body><w:tbl>
  <w:tblGrid><w:gridCol w:w="450"/><w:gridCol w:w="1800"/><w:gridCol w:w="900"/></w:tblGrid>
  <w:tr><w:tc><w:tcPr><w:gridSpan w:val="3"/></w:tcPr><w:p/></w:tc></w:tr>
  <w:tr><w:tc><w:p/></w:tc><w:tc><w:p/></w:tc>
    <w:tc><w:tcPr><w:vMerge w:val="restart"/><w:textDirection w:val="tbRl"/></w:tcPr><w:p/></w:tc></w:tr>
  <w:tr><w:tc><w:p/></w:tc><w:tc><w:p/></w:tc>
    <w:tc><w:tcPr><w:vMerge/></w:tcPr><w:p/></w:tc></w:tr>
</w:tbl></w:body></w:document>`

// What mammoth makes of it: the merge becomes a rowspan, widths are gone.
const MAMMOTH_HTML = '<table>'
  + '<tr><td colspan="3"><p>Title</p></td></tr>'
  + '<tr><td><p>1</p></td><td><p>Ірина РУДАКОВА</p></td><td rowspan="2"><p>Address</p></td></tr>'
  + '<tr><td><p>2</p></td><td><p>Юрій ЗАХАРЧУК</p></td></tr>'
  + '</table>'

describe('RichText table cells', () => {
  it('puts Word column widths and text direction back onto mammoth tables', () => {
    const editor = editorWith(applyDocxTableLayout(MAMMOTH_HTML, DOCUMENT_XML))
    const attrs = cellAttrs(editor)
    expect(attrs.map(a => a.colwidth)).toEqual([[30, 120, 60], [30], [120], [60], [30], [120]])
    expect(attrs.map(a => a.textDirection)).toEqual([null, null, null, 'tb', null, null])

    const html = editor.getHTML()
    expect(html).toContain('rowspan="2" colwidth="60" style="writing-mode: vertical-rl;"')
    expect(html).toContain('<col style="width: 120px;">')
    // survives a save / reload round trip
    expect(cellAttrs(editorWith(html))).toEqual(attrs)
  })

  it('leaves mammoth output alone when the tables do not line up', () => {
    expect(applyDocxTableLayout('<p>no tables</p>', DOCUMENT_XML)).toBe('<p>no tables</p>')
  })

  it('reads vertical text and widths from Word clipboard HTML', () => {
    const editor = editorWith('<table><tr>'
      + '<td width="160"><p>a</p></td>'
      + '<td width="60" style="width:45pt;layout-flow:vertical"><p>b</p></td>'
      + '<td style="layout-flow:vertical;mso-layout-flow-alt:bottom-to-top"><p>c</p></td>'
      + '<td width="100%"><p>d</p></td>'
      + '</tr></table>')
    const attrs = cellAttrs(editor)
    expect(attrs.map(a => a.textDirection)).toEqual([null, 'tb', 'bt', null])
    expect(attrs.map(a => a.colwidth)).toEqual([[160], [60], null, null])
  })
})
