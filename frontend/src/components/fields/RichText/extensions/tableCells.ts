import { TableCell, TableHeader } from '@tiptap/extension-table'

// Table cell attributes: Word column widths, vertical text, shading, vertical alignment
// A cell's text direction is stored as `writing-mode` in its style (the
// sanitizer allows it), so saved HTML renders vertically on public pages too:
//   'tb' - top to bottom (Word «tbRl», text turned 90° clockwise)
//   'bt' - bottom to top (Word «btLr», text turned 90° counter-clockwise)
export type TextDirection = 'tb' | 'bt'

export const TEXT_DIRECTIONS: (TextDirection | null)[] = [null, 'tb', 'bt']

export const WRITING_MODE: Record<TextDirection, string> = { tb: 'vertical-rl', bt: 'sideways-lr' }

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

// Shading and vertical alignment are plain inline styles too (both on the
// sanitizer's allowlist), set from the table bubble menu.
const styleAttribute = (name: string, prop: string) => ({
  default: null,
  parseHTML: (el: HTMLElement) => el.style.getPropertyValue(prop) || null,
  renderHTML: (attrs: Record<string, any>) => (attrs[name] ? { style: `${prop}: ${attrs[name]}` } : {}),
})

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
  backgroundColor: styleAttribute('backgroundColor', 'background-color'),
  verticalAlign: styleAttribute('verticalAlign', 'vertical-align'),
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

