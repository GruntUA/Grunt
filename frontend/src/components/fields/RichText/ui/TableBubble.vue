<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useEventListener } from '@vueuse/core'
import { BubbleMenu } from '@tiptap/vue-3/menus'
import type { Editor } from '@tiptap/core'
import { ChevronDown, PaintBucket, SquareDashed, Trash2 } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { N_ } from '@/plugins/i18n'
import { useRichEditorContext } from '../editor/useRichEditor'
import CommandButton from './CommandButton.vue'
import CommandMenuItem from './CommandMenuItem.vue'

// Table tools while the cursor is in a table. The menu sits over the table's
// top edge - or right under the sticky toolbar once that edge scrolls away -
// so it never covers the row being edited.
const { t } = useI18n()
const { editor, refocus } = useRichEditorContext()

const PLUGIN_KEY = 'tableBubble'
const BUBBLE_HEIGHT = 48

// Translucent, so shading reads on both the light site and the dark editor.
const SHADES = [
  { label: N_('Gray'), value: 'rgba(148, 163, 184, 0.2)' },
  { label: N_('Yellow'), value: 'rgba(234, 179, 8, 0.2)' },
  { label: N_('Green'), value: 'rgba(34, 197, 94, 0.18)' },
  { label: N_('Blue'), value: 'rgba(59, 130, 246, 0.18)' },
  { label: N_('Red'), value: 'rgba(239, 68, 68, 0.18)' },
  { label: N_('Purple'), value: 'rgba(168, 85, 247, 0.18)' },
]

const shouldShow = ({ editor: e }: { editor: Editor }) => e.isEditable && e.view.hasFocus() && e.isActive('table')

function anchor() {
  const e = editor.value
  if (!e) return null
  const at = e.view.domAtPos(e.state.selection.from).node
  const table = (at instanceof Element ? at : at.parentElement)?.closest('table')
  if (!table) return null
  const toolbar = table.closest('[data-richtext]')?.querySelector('[role=toolbar]')
  const rect = () => {
    const r = table.getBoundingClientRect()
    const floor = (toolbar?.getBoundingClientRect().bottom ?? 0) + BUBBLE_HEIGHT
    return new DOMRect(r.left, Math.min(Math.max(r.top, floor), r.bottom), r.width, 0)
  }
  return { getBoundingClientRect: rect, getClientRects: () => [rect()] }
}

// The anchor depends on scroll position (any scroll container), so re-place on scroll.
useEventListener(window, 'scroll', () => {
  const e = editor.value
  if (e?.isActive('table')) e.view.dispatch(e.state.tr.setMeta(PLUGIN_KEY, 'updatePosition'))
}, { capture: true, passive: true })

const shade = (value: string | null) => editor.value?.chain().focus().setCellAttribute('backgroundColor', value).run()
</script>

<template>
  <BubbleMenu
    v-if="editor" :editor :plugin-key="PLUGIN_KEY" :should-show :get-referenced-virtual-element="anchor"
    :options="{ placement: 'top-start', offset: 6 }"
    class="richtext-bubble z-20 flex items-center gap-0.5 rounded-md border border-border bg-popover p-1 text-muted-foreground shadow-md"
  >
    <CommandButton id="addRowBefore" />
    <CommandButton id="addRowAfter" />
    <CommandButton id="addColumnBefore" />
    <CommandButton id="addColumnAfter" />
    <Separator orientation="vertical" class="!mx-1 !h-6 !my-0" />
    <CommandButton id="mergeCells" />
    <CommandButton id="splitCell" />
    <CommandButton id="toggleHeaderRow" />
    <CommandButton id="toggleHeaderColumn" />
    <Separator orientation="vertical" class="!mx-1 !h-6 !my-0" />

    <!-- Cell: alignment, text direction, shading -->
    <DropdownMenu>
      <DropdownMenuTrigger as-child>
        <Button size="sm" variant="ghost" class="gap-0.5 px-1.5" :title="t('Cell')" :aria-label="t('Cell')">
          <PaintBucket />
          <ChevronDown class="size-3 opacity-60" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" class="w-64" @close-auto-focus="refocus">
        <CommandMenuItem id="cellAlignTop" />
        <CommandMenuItem id="cellAlignMiddle" />
        <CommandMenuItem id="cellAlignBottom" />
        <DropdownMenuSeparator />
        <CommandMenuItem id="textHorizontal" />
        <CommandMenuItem id="textTopToBottom" />
        <CommandMenuItem id="textBottomToTop" />
        <DropdownMenuSeparator />
        <DropdownMenuLabel class="text-muted-foreground">{{ t('Shading') }}</DropdownMenuLabel>
        <div class="flex gap-1 px-2 pb-1.5">
          <DropdownMenuItem
            class="size-6 justify-center rounded-sm border border-border p-0"
            :title="t('No shading')" :aria-label="t('No shading')" @select="shade(null)"
          >
            <SquareDashed />
          </DropdownMenuItem>
          <DropdownMenuItem
            v-for="s in SHADES" :key="s.value"
            class="size-6 rounded-sm border border-border p-0" :style="{ background: s.value }"
            :title="t(s.label)" :aria-label="t(s.label)" @select="shade(s.value)"
          />
        </div>
      </DropdownMenuContent>
    </DropdownMenu>

    <!-- Delete -->
    <DropdownMenu>
      <DropdownMenuTrigger as-child>
        <Button size="sm" variant="ghost" class="gap-0.5 px-1.5 hover:text-destructive" :title="t('Delete')" :aria-label="t('Delete')">
          <Trash2 />
          <ChevronDown class="size-3 opacity-60" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" class="w-48" @close-auto-focus="refocus">
        <CommandMenuItem id="deleteRow" />
        <CommandMenuItem id="deleteColumn" />
        <DropdownMenuSeparator />
        <CommandMenuItem id="deleteTable" />
      </DropdownMenuContent>
    </DropdownMenu>
  </BubbleMenu>
</template>
