import { TableCell, TableHeader } from '@tiptap/extension-table'

// ── Vertical text & Word column widths in table cells ────────────────────────
// A cell's text direction is stored as `writing-mode` in its style (the
// sanitizer allows it), so saved HTML renders vertically on public pages too:
//   'tb' — top to bottom (Word «tbRl», text turned 90° clockwise)
//   'bt' — bottom to top (Word «btLr», text turned 90° counter-clockwise)
export type TextDirection = 'tb' | 'bt'

export const TEXT_DIRECTIONS: (TextDirection | null)[] = [null, 'tb', 'bt']

const WRITING_MODE: Record<TextDirection, string> = { tb: 'vertical-rl', bt: 'sideways-lr' }

// The browser's CSSOM drops properties it doesn't know (Word's `layout-flow`),
// so styles are read from the raw attribute.
function styleProp(el: HTMLElement, prop: string): string {
  const m = (el.getAttribute('style') ?? '').match(new RegExp(`(?:^|;)\\s*${prop}\\s*:\\s*([^;]+)`, 'i'))
  return m ? m[1].trim().toLowerCase() : ''
}

function parseTextDirection(el: HTMLElement): TextDirection | null {
  const mode = styleProp(el, 'writing-mode')
  if (mode === 'sideways-lr') return 'bt'
  if (mode.startsWith('vertical') || mode === 'sideways-rl' || mode.startsWith('tb')) return 'tb'
  // Word's clipboard HTML: layout-flow:vertical [+ mso-layout-flow-alt:bottom-to-top]
  if (styleProp(el, 'layout-flow').startsWith('vertical'))
    return styleProp(el, 'mso-layout-flow-alt') === 'bottom-to-top' ? 'bt' : 'tb'
  return null
}

// tiptap reads `colwidth` / <colgroup>; content pasted from Word carries the
// width as a plain pixel `width` attribute on the cell instead.
function parseColwidth(el: HTMLElement): number[] | null {
  const own = el.getAttribute('colwidth')
  if (own) return own.split(',').map(w => parseInt(w, 10))
  const row = el.parentElement
  const table = el.closest('table')
  if (row && table) {
    const col = table.querySelectorAll('colgroup > col')[Array.from(row.children).indexOf(el)]
    const w = col?.getAttribute('width')
    if (w && /^\d+$/.test(w)) return [parseInt(w, 10)]
  }
  const width = el.getAttribute('width')
  if (width && /^\d+$/.test(width)) {
    const span = parseInt(el.getAttribute('colspan') ?? '1', 10) || 1
    const each = Math.round(parseInt(width, 10) / span)
    return Array.from({ length: span }, () => each)
  }
  return null
}

const cellAttributes = {
  colwidth: { default: null, parseHTML: parseColwidth },
  textDirection: {
    default: null,
    parseHTML: parseTextDirection,
    renderHTML: (attrs: Record<string, any>) => {
      const mode = WRITING_MODE[attrs.textDirection as TextDirection]
      return mode ? { style: `writing-mode: ${mode}` } : {}
    },
  },
}

export const RichTableCell = TableCell.extend({
  addAttributes() {
    return { ...this.parent?.(), ...cellAttributes }
  },
})

export const RichTableHeader = TableHeader.extend({
  addAttributes() {
    return { ...this.parent?.(), ...cellAttributes }
  },
})

// ── .docx import ─────────────────────────────────────────────────────────────
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
