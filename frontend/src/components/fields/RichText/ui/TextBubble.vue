<script setup lang="ts">
import { NodeSelection } from '@tiptap/pm/state'
import { CellSelection } from '@tiptap/pm/tables'
import { BubbleMenu } from '@tiptap/vue-3/menus'
import type { Editor } from '@tiptap/core'
import { useEditorInstance } from '../editor/useRichEditor'
import CommandButton from './CommandButton.vue'
import LinkPopover from './LinkPopover.vue'

// Quick formatting over a text selection.
const editor = useEditorInstance()

function shouldShow({ editor: e }: { editor: Editor }) {
  const { selection } = e.state
  return e.isEditable && e.view.hasFocus() && !selection.empty
    && !(selection instanceof NodeSelection) && !(selection instanceof CellSelection)
    && !e.isActive('codeBlock')
}
</script>

<template>
  <BubbleMenu
    v-if="editor" :editor plugin-key="textBubble" :should-show
    class="richtext-bubble z-20 flex items-center gap-0.5 rounded-md border border-border bg-popover p-1 text-muted-foreground shadow-md"
  >
    <CommandButton id="bold" />
    <CommandButton id="italic" />
    <CommandButton id="underline" />
    <CommandButton id="strike" />
    <CommandButton id="highlight" />
    <LinkPopover />
  </BubbleMenu>
</template>
