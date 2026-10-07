import Image from '@tiptap/extension-image'

// Images keep their layout as inline styles (on the sanitizer's allowlist), so
// a saved page shows them the same without any site CSS:
//   size  - width in % of the text column ('25%' … '100%'), null = natural size
//   align - 'left' / 'right' float with text wrapping around, 'center' on its own line
export type ImageAlign = 'left' | 'center' | 'right'

export const IMAGE_SIZES = ['25%', '50%', '75%', '100%'] as const

const ALIGN_STYLE: Record<ImageAlign, string> = {
  left: 'float: left; margin-right: 1em',
  center: 'display: block; margin-left: auto; margin-right: auto',
  right: 'float: right; margin-left: 1em',
}

function parseAlign(el: HTMLElement): ImageAlign | null {
  const float = el.style.float
  if (float === 'left' || float === 'right') return float
  return el.style.display === 'block' && el.style.marginLeft === 'auto' ? 'center' : null
}

export const RichImage = Image.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      size: {
        default: null,
        parseHTML: (el: HTMLElement) => (el.style.width.endsWith('%') ? el.style.width : null),
        renderHTML: (attrs: Record<string, any>) => (attrs.size ? { style: `width: ${attrs.size}` } : {}),
      },
      align: {
        default: null,
        parseHTML: parseAlign,
        renderHTML: (attrs: Record<string, any>) => (attrs.align ? { style: ALIGN_STYLE[attrs.align as ImageAlign] } : {}),
      },
    }
  },
}).configure({ inline: false })
