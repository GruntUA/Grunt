<script setup lang="ts">
import { nextTick, ref, useTemplateRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { TextSelection } from '@tiptap/pm/state'
import {
  AlignLeft, Clipboard, Copy, Link as LinkIcon, PaintBucket, Pencil, Pilcrow, Scissors, SquareDashed,
  Table as TableIcon, Type,
} from '@lucide/vue'
import {
  ContextMenu, ContextMenuContent, ContextMenuItem, ContextMenuLabel, ContextMenuSeparator, ContextMenuShortcut,
  ContextMenuSub, ContextMenuSubContent, ContextMenuSubTrigger, ContextMenuTrigger,
} from '@/components/ui/context-menu'
import { useToast } from '@/core/composables/useToast'
import { N_ } from '@/plugins/i18n'
import { ALIGNMENTS, BLOCK_STYLES } from '../editor/commands'
import { useRichEditorContext } from '../editor/useRichEditor'
import CommandMenuItem from './CommandMenuItem.vue'
import LinkPopover from './LinkPopover.vue'

// Right-click menu of the text: clipboard, formatting, and the table tools
// when the click is in a table. Shift + right-click keeps the browser's own
// menu (spelling suggestions).
const { t } = useI18n()
const toast = useToast()
const { editor, editable } = useRichEditorContext()

const linkPopover = useTemplateRef<InstanceType<typeof LinkPopover>>('linkPopover')
const at = ref({ x: 0, y: 0 })
// What the click landed on - read once, when the menu opens.
const where = ref({ selection: false, link: false, table: false })
let openLink = false

// Cell shading. Translucent, so it reads on both the light site and the dark editor.
const SHADES = [
  { label: N_('Gray'), value: 'rgba(148, 163, 184, 0.2)' },
  { label: N_('Yellow'), value: 'rgba(234, 179, 8, 0.2)' },
  { label: N_('Green'), value: 'rgba(34, 197, 94, 0.18)' },
  { label: N_('Blue'), value: 'rgba(59, 130, 246, 0.18)' },
  { label: N_('Red'), value: 'rgba(239, 68, 68, 0.18)' },
  { label: N_('Purple'), value: 'rgba(168, 85, 247, 0.18)' },
]

const shade = (value: string | null) => editor.value?.chain().focus().setCellAttribute('backgroundColor', value).run()

function onContextMenu(event: MouseEvent) {
  const e = editor.value
  if (event.shiftKey || !e || !editable()) {
    event.stopPropagation() // the browser's menu, not ours
    return
  }
  // A click outside the selection moves the cursor there, as in a word processor.
  const pos = e.view.posAtCoords({ left: event.clientX, top: event.clientY })?.pos
  const { from, to } = e.state.selection
  if (pos !== undefined && (pos < from || pos > to)) {
    e.view.dispatch(e.state.tr.setSelection(TextSelection.near(e.state.doc.resolve(pos))))
  }
  e.view.focus()
  at.value = { x: event.clientX, y: event.clientY }
}

// Also reached by a long press on touch screens.
function onOpen(open: boolean) {
  const e = editor.value
  if (open && e) where.value = { selection: !e.state.selection.empty, link: e.isActive('link'), table: e.isActive('table') }
}

function onCloseAutoFocus(event: Event) {
  event.preventDefault()
  editor.value?.commands.focus()
  if (openLink) {
    openLink = false
    nextTick(() => linkPopover.value?.show())
  }
}

/** Cut / copy go through the browser, so ProseMirror serializes the selection as usual. */
function clipboard(action: 'cut' | 'copy') {
  editor.value?.commands.focus()
  document.execCommand(action)
}

async function paste() {
  const e = editor.value
  if (!e) return
  try {
    for (const item of await navigator.clipboard.read()) {
      if (item.types.includes('text/html')) {
        e.view.pasteHTML(await (await item.getType('text/html')).text())
        return
      }
      if (item.types.includes('text/plain')) {
        e.view.pasteText(await (await item.getType('text/plain')).text())
        return
      }
    }
  } catch {
    // No clipboard permission (or no API): the keyboard always works.
    toast.warning(t('The browser did not allow reading the clipboard. Use Ctrl+V.'))
  }
}
</script>

<template>
  <ContextMenu @update:open="onOpen">
    <ContextMenuTrigger as-child @contextmenu.capture="onContextMenu">
      <slot />
    </ContextMenuTrigger>
    <ContextMenuContent class="w-64" @close-auto-focus="onCloseAutoFocus">
      <ContextMenuItem :disabled="!where.selection" @select="clipboard('cut')">
        <Scissors />{{ t('Cut') }}<ContextMenuShortcut>Ctrl+X</ContextMenuShortcut>
      </ContextMenuItem>
      <ContextMenuItem :disabled="!where.selection" @select="clipboard('copy')">
        <Copy />{{ t('Copy') }}<ContextMenuShortcut>Ctrl+C</ContextMenuShortcut>
      </ContextMenuItem>
      <ContextMenuItem @select="paste">
        <Clipboard />{{ t('Paste') }}<ContextMenuShortcut>Ctrl+V</ContextMenuShortcut>
      </ContextMenuItem>
      <ContextMenuSeparator />

      <CommandMenuItem id="bold" context />
      <CommandMenuItem id="italic" context />
      <CommandMenuItem id="underline" context />
      <CommandMenuItem id="strike" context />
      <CommandMenuItem id="highlight" context />
      <ContextMenuSub>
        <ContextMenuSubTrigger><Type />{{ t('More') }}</ContextMenuSubTrigger>
        <ContextMenuSubContent class="w-56">
          <CommandMenuItem id="superscript" context />
          <CommandMenuItem id="subscript" context />
          <CommandMenuItem id="code" context />
        </ContextMenuSubContent>
      </ContextMenuSub>
      <ContextMenuSeparator />

      <ContextMenuItem @select="openLink = true">
        <component :is="where.link ? Pencil : LinkIcon" />{{ t(where.link ? 'Edit link' : 'Link') }}
      </ContextMenuItem>
      <CommandMenuItem v-if="where.link" id="unsetLink" context />
      <ContextMenuSeparator />

      <ContextMenuSub>
        <ContextMenuSubTrigger><Pilcrow />{{ t('Text style') }}</ContextMenuSubTrigger>
        <ContextMenuSubContent class="w-56">
          <CommandMenuItem v-for="id in BLOCK_STYLES" :key="id" :id context />
          <ContextMenuSeparator />
          <CommandMenuItem id="bulletList" context />
          <CommandMenuItem id="orderedList" context />
        </ContextMenuSubContent>
      </ContextMenuSub>
      <ContextMenuSub>
        <ContextMenuSubTrigger><AlignLeft />{{ t('Alignment') }}</ContextMenuSubTrigger>
        <ContextMenuSubContent class="w-56">
          <CommandMenuItem v-for="id in ALIGNMENTS" :key="id" :id context />
          <ContextMenuSeparator />
          <CommandMenuItem id="indent" context />
          <CommandMenuItem id="outdent" context />
        </ContextMenuSubContent>
      </ContextMenuSub>

      <template v-if="where.table">
        <ContextMenuSeparator />
        <ContextMenuSub>
          <ContextMenuSubTrigger><TableIcon />{{ t('Table') }}</ContextMenuSubTrigger>
          <ContextMenuSubContent class="w-60">
            <CommandMenuItem id="addRowBefore" context />
            <CommandMenuItem id="addRowAfter" context />
            <CommandMenuItem id="addColumnBefore" context />
            <CommandMenuItem id="addColumnAfter" context />
            <ContextMenuSeparator />
            <CommandMenuItem id="mergeCells" context />
            <CommandMenuItem id="splitCell" context />
            <CommandMenuItem id="toggleHeaderRow" context />
            <CommandMenuItem id="toggleHeaderColumn" context />
            <ContextMenuSeparator />
            <CommandMenuItem id="deleteRow" context />
            <CommandMenuItem id="deleteColumn" context />
            <CommandMenuItem id="deleteTable" context />
          </ContextMenuSubContent>
        </ContextMenuSub>
        <ContextMenuSub>
          <ContextMenuSubTrigger><PaintBucket />{{ t('Cell') }}</ContextMenuSubTrigger>
          <ContextMenuSubContent class="w-64">
            <CommandMenuItem id="cellAlignTop" context />
            <CommandMenuItem id="cellAlignMiddle" context />
            <CommandMenuItem id="cellAlignBottom" context />
            <ContextMenuSeparator />
            <CommandMenuItem id="textHorizontal" context />
            <CommandMenuItem id="textTopToBottom" context />
            <CommandMenuItem id="textBottomToTop" context />
            <ContextMenuSeparator />
            <ContextMenuLabel class="text-muted-foreground">{{ t('Shading') }}</ContextMenuLabel>
            <div class="flex gap-1 px-2 pb-1.5">
              <ContextMenuItem
                class="size-6 justify-center rounded-sm border border-border p-0"
                :title="t('No shading')" :aria-label="t('No shading')" @select="shade(null)"
              >
                <SquareDashed />
              </ContextMenuItem>
              <ContextMenuItem
                v-for="s in SHADES" :key="s.value"
                class="size-6 rounded-sm border border-border p-0" :style="{ background: s.value }"
                :title="t(s.label)" :aria-label="t(s.label)" @select="shade(s.value)"
              />
            </div>
          </ContextMenuSubContent>
        </ContextMenuSub>
      </template>
    </ContextMenuContent>
  </ContextMenu>

  <LinkPopover ref="linkPopover" :at />
</template>
