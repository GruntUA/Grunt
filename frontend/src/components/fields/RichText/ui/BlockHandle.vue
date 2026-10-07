<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { DragHandle } from '@tiptap/extension-drag-handle-vue-3'
import type { Node as PmNode } from '@tiptap/pm/model'
import { Copy, GripVertical, Trash2 } from '@lucide/vue'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { BLOCK_STYLES, command } from '../editor/commands'
import { useRichEditorContext } from '../editor/useRichEditor'

// ⋮⋮ left of the hovered block: drag to move it, click for a menu
// (turn into another block style, duplicate, delete).
const { t } = useI18n()
const { editor, refocus } = useRichEditorContext()

const block = ref<{ node: PmNode; pos: number } | null>(null)
const menuOpen = ref(false)

function onNodeChange({ node, pos }: { node: PmNode | null; pos: number }) {
  if (!menuOpen.value) block.value = node ? { node, pos } : null
}

// The handle must not jump to another block while its menu is open.
function setMenuOpen(open: boolean) {
  menuOpen.value = open
  editor.value?.commands.setMeta('lockDragHandle', open)
}

function turnInto(id: (typeof BLOCK_STYLES)[number]) {
  const e = editor.value
  if (!e || !block.value) return
  command(id).run(e.chain().focus().setTextSelection(block.value.pos + 1), e).run()
}

function duplicate() {
  const { node, pos } = block.value!
  editor.value?.chain().focus().insertContentAt(pos + node.nodeSize, node.toJSON()).run()
}

function remove() {
  const { node, pos } = block.value!
  editor.value?.chain().focus().deleteRange({ from: pos, to: pos + node.nodeSize }).run()
}
</script>

<template>
  <DragHandle v-if="editor" :editor :on-node-change class="richtext-drag-handle">
    <DropdownMenu :open="menuOpen" @update:open="setMenuOpen">
      <!-- The menu opens on click, not on pointerdown, so dragging the handle still works. -->
      <DropdownMenuTrigger as-child>
        <span class="pointer-events-none absolute inset-0" aria-hidden="true" />
      </DropdownMenuTrigger>
      <button
        type="button" :title="t('Drag to move, click for options')" :aria-label="t('Block options')"
        class="flex h-6 w-5 cursor-grab items-center justify-center rounded-sm text-muted-foreground hover:bg-accent hover:text-foreground"
        @click="setMenuOpen(true)"
      >
        <GripVertical class="size-4" />
      </button>
      <DropdownMenuContent align="start" side="left" class="w-52" @close-auto-focus="refocus">
        <template v-if="block?.node.isTextblock">
          <DropdownMenuLabel class="text-muted-foreground">{{ t('Turn into') }}</DropdownMenuLabel>
          <DropdownMenuItem v-for="id in BLOCK_STYLES" :key="id" @select="turnInto(id)">
            <component :is="command(id).icon" /> {{ t(command(id).label) }}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
        </template>
        <DropdownMenuItem @select="duplicate"><Copy /> {{ t('Duplicate') }}</DropdownMenuItem>
        <DropdownMenuItem variant="destructive" @select="remove"><Trash2 /> {{ t('Delete') }}</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  </DragHandle>
</template>
