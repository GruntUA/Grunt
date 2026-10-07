import { Extension, type Editor, type Range } from '@tiptap/core'
import Suggestion from '@tiptap/suggestion'
import type { Component } from 'vue'

/**
 * "/" menu: type a slash, then filter blocks to insert by name.
 *
 * The extension only drives a plain state object (`SlashMenuState`); the popup
 * itself is an ordinary component (ui/SlashMenu.vue) rendering that state.
 */
export interface SlashItem {
  id: string
  label: string
  icon: Component
  /** Extra words the filter matches (English id, synonyms). */
  keywords?: string
  run: (editor: Editor, range: Range) => void
}

export interface SlashMenuState {
  items: SlashItem[]
  index: number
  rect: (() => DOMRect | null) | null
  choose: ((item: SlashItem) => void) | null
}

export interface SlashOptions {
  items: () => SlashItem[]
  state: SlashMenuState
}

const matches = (item: SlashItem, query: string) =>
  `${item.label} ${item.id} ${item.keywords ?? ''}`.toLowerCase().includes(query.toLowerCase())

export const SlashCommands = Extension.create<SlashOptions>({
  name: 'slashCommands',

  addProseMirrorPlugins() {
    const { state } = this.options
    const close = () => Object.assign(state, { items: [], index: 0, rect: null, choose: null })

    return [Suggestion<SlashItem, SlashItem>({
      editor: this.editor,
      char: '/',
      items: ({ query }) => this.options.items().filter(item => matches(item, query)),
      command: ({ editor, range, props: item }) => item.run(editor, range),
      render: () => ({
        onStart: (p) => Object.assign(state, { items: p.items, index: 0, rect: p.clientRect ?? null, choose: p.command }),
        onUpdate: (p) => Object.assign(state, { items: p.items, index: 0, rect: p.clientRect ?? null, choose: p.command }),
        onExit: close,
        onKeyDown: ({ event }) => {
          const n = state.items.length
          if (!n) return false
          if (event.key === 'ArrowDown') state.index = (state.index + 1) % n
          else if (event.key === 'ArrowUp') state.index = (state.index + n - 1) % n
          else if (event.key === 'Enter' || event.key === 'Tab') state.choose?.(state.items[state.index]!)
          else if (event.key === 'Escape') close()
          else return false
          return true
        },
      }),
    })]
  },
})
