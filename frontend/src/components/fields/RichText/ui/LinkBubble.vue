<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { BubbleMenu } from '@tiptap/vue-3/menus'
import type { Editor } from '@tiptap/core'
import { ExternalLink, Pencil } from '@lucide/vue'
import { N_ } from '@/plugins/i18n'
import { useEditorInstance } from '../editor/useRichEditor'
import CommandButton from './CommandButton.vue'
import LinkPopover from './LinkPopover.vue'

// The link under the cursor: where it goes, edit, remove.
const { t } = useI18n()
const editor = useEditorInstance()

const href = computed(() => editor.value?.getAttributes('link').href as string | undefined)

const shouldShow = ({ editor: e }: { editor: Editor }) =>
  e.isEditable && e.view.hasFocus() && e.state.selection.empty && e.isActive('link')
</script>

<template>
  <BubbleMenu
    v-if="editor" :editor plugin-key="linkBubble" :should-show :options="{ placement: 'bottom-start', offset: 6 }"
    class="richtext-bubble z-20 flex max-w-sm items-center gap-0.5 rounded-md border border-border bg-popover p-1 text-muted-foreground shadow-md"
  >
    <a
      :href target="_blank" rel="noopener noreferrer" :title="t('Open link')"
      class="flex min-w-0 items-center gap-1.5 rounded-sm px-2 py-1 text-primary hover:bg-accent"
    >
      <ExternalLink class="size-3.5 shrink-0" />
      <span class="truncate">{{ href }}</span>
    </a>
    <LinkPopover :icon="Pencil" :label="N_('Edit link')" />
    <CommandButton id="unsetLink" />
  </BubbleMenu>
</template>
