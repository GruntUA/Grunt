import { WRITING_MODE, type TextDirection } from './tableCells'

// .docx import
// mammoth converts the document body to HTML; tables then get their Word layout back.
// mammoth keeps table structure (colspan / rowspan) but drops column widths
// and text direction. They are read from word/document.xml and put back onto
// mammoth's HTML: tables match in document order, and the cells of a row in
// order once vertically-merged continuation cells (which mammoth folds into a
// rowspan) are skipped. Anything that doesn't line up is left as mammoth made it.
const W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

interface DocxCell { widths: number[]; direction: TextDirection | null }

const children = (el: Element, name: string) =>
  Array.from(el.children).filter(c => c.namespaceURI === W && c.localName === name)
const child = (el: Element | undefined, name: string) => (el ? children(el, name)[0] : undefined)
const wVal = (el: Element | undefined) => el?.getAttributeNS(W, 'val') ?? null

const TWIPS_PER_PX = 15

function docxDirection(tcPr: Element | undefined): TextDirection | null {
  const v = wVal(child(tcPr, 'textDirection'))
  if (!v) return null
  if (v === 'btLr') return 'bt'
  if (['tbRl', 'tbRlV', 'tbLrV', 'tb'].includes(v)) return 'tb'
  return null
}

function readDocxTable(tbl: Element): DocxCell[][] {
  const grid = children(child(tbl, 'tblGrid') ?? tbl, 'gridCol')
    .map(c => Math.round(parseInt(c.getAttributeNS(W, 'w') ?? '0', 10) / TWIPS_PER_PX))
  return children(tbl, 'tr').map((tr) => {
    let col = parseInt(wVal(child(child(tr, 'trPr'), 'gridBefore')) ?? '0', 10) || 0
    const cells: DocxCell[] = []
    for (const tc of children(tr, 'tc')) {
      const tcPr = child(tc, 'tcPr')
      const span = parseInt(wVal(child(tcPr, 'gridSpan')) ?? '1', 10) || 1
      const vMerge = child(tcPr, 'vMerge')
      const isContinuation = !!vMerge && wVal(vMerge) !== 'restart'
      if (!isContinuation)
        cells.push({ widths: grid.slice(col, col + span).filter(w => w > 0), direction: docxDirection(tcPr) })
      col += span
    }
    return cells
  })
}

export function applyDocxTableLayout(html: string, documentXml: string): string {
  const xml = new DOMParser().parseFromString(documentXml, 'application/xml')
  const docxTables = Array.from(xml.getElementsByTagNameNS(W, 'tbl')).map(readDocxTable)

  const doc = new DOMParser().parseFromString(`<body>${html}</body>`, 'text/html')
  const htmlTables = Array.from(doc.querySelectorAll('table'))
  if (!htmlTables.length || htmlTables.length !== docxTables.length) return html

  htmlTables.forEach((table, t) => {
    const rows = Array.from(table.rows)
    if (rows.length !== docxTables[t].length) return
    rows.forEach((tr, r) => {
      const source = docxTables[t][r]
      const cells = Array.from(tr.cells)
      if (cells.length !== source.length) return
      cells.forEach((cell, i) => {
        const { widths, direction } = source[i]
        if (widths.length === cell.colSpan) cell.setAttribute('colwidth', widths.join(','))
        if (direction) {
          const style = cell.getAttribute('style')
          cell.setAttribute('style', `${style ? `${style}; ` : ''}writing-mode: ${WRITING_MODE[direction]}`)
        }
      })
    })
  })
  return doc.body.innerHTML
}

export async function readDocxDocumentXml(data: ArrayBuffer): Promise<string | null> {
  const { default: JSZip } = await import('jszip')
  const zip = await JSZip.loadAsync(data)
  return (await zip.file('word/document.xml')?.async('string')) ?? null
}

export interface DocxImport { html: string; warnings: string[] }

/** Convert a .docx file to editor HTML (mammoth + Word table layout). */
export async function docxToHtml(file: File): Promise<DocxImport> {
  const arrayBuffer = await file.arrayBuffer()
  // `mammoth` (~200 kB, pulls jszip) is loaded on demand only.
  const { default: mammoth } = await import('mammoth')
  const { value: html, messages } = await mammoth.convertToHtml({ arrayBuffer })
  const documentXml = await readDocxDocumentXml(arrayBuffer).catch(() => null)
  return {
    html: documentXml ? applyDocxTableLayout(html, documentXml) : html,
    warnings: messages.filter(m => m.type === 'error').map(m => m.message),
  }
}
