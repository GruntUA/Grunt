import { Extension } from '@tiptap/core'

// Paragraph indent, stored as margin-left in steps of INDENT_STEP px (Word-like
// "Increase indent"). Tab / Shift-Tab indent outside lists; in a list they nest.
const INDENT_STEP = 40
const MAX_INDENT = 7
const INDENT_TYPES = ['paragraph', 'heading', 'blockquote']

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    indent: {
      indent: () => ReturnType
      outdent: () => ReturnType
    }
  }
}

export const Indent = Extension.create({
  name: 'indent',

  addGlobalAttributes() {
    return [{
      types: INDENT_TYPES,
      attributes: {
        indent: {
          default: 0,
          parseHTML: (el) => Math.round((parseInt(el.style.marginLeft, 10) || 0) / INDENT_STEP),
          renderHTML: (attrs) => (attrs.indent > 0 ? { style: `margin-left: ${attrs.indent * INDENT_STEP}px` } : {}),
        },
      },
    }]
  },

  addCommands() {
    const shift = (delta: number) => () => ({ state, tr, dispatch }: any) => {
      const { from, to } = state.selection
      state.doc.nodesBetween(from, to, (node: any, pos: number) => {
        if (!INDENT_TYPES.includes(node.type.name)) return
        const indent = Math.min(Math.max((node.attrs.indent || 0) + delta, 0), MAX_INDENT)
        tr.setNodeMarkup(pos, undefined, { ...node.attrs, indent })
      })
      if (dispatch) dispatch(tr)
      return true
    }
    return { indent: shift(1), outdent: shift(-1) }
  },

  addKeyboardShortcuts() {
    const outsideList = (run: () => boolean) => () => !this.editor.isActive('listItem') && run()
    return {
      Tab: outsideList(() => this.editor.commands.indent()),
      'Shift-Tab': outsideList(() => this.editor.commands.outdent()),
    }
  },
})
