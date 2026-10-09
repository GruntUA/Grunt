<script setup lang="ts">
import { computed, ref, type Component } from 'vue'
import { getMarkRange } from '@tiptap/core'
import { useI18n } from 'vue-i18n'
import { FileSymlink, Link as LinkIcon, Link2Off } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Popover, PopoverAnchor, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { useRichEditorContext } from '../editor/useRichEditor'

// Link button + its URL form. Used by the toolbar, (as "Edit link") the link
// bubble and - without a button, opened by show() at a point - the right-click menu.
const props = defineProps<{ icon?: Component; label?: string; at?: { x: number; y: number } }>()

const { t } = useI18n()
const title = computed(() => t(props.label ?? 'Link'))
const { editor, linkToFile } = useRichEditorContext()

const open = ref(false)
const url = ref('')
const text = ref('')
// What the link covers: the whole link under the cursor, else the selection.
let range = { from: 0, to: 0 }
let originalText = ''

function onOpen(value: boolean) {
  const e = editor.value
  if (value && e) {
    const { state } = e
    const { from, to } = state.selection
    range = getMarkRange(state.selection.$from, state.schema.marks.link) ?? { from, to }
    originalText = state.doc.textBetween(range.from, range.to, ' ')
    text.value = originalText
    url.value = e.getAttributes('link').href ?? ''
  }
  open.value = value
}

function apply() {
  const e = editor.value
  if (!e) return
  const href = url.value.trim()
  const label = text.value.trim()
  if (!href) {
    e.chain().focus().setTextSelection(range).extendMarkRange('link').unsetLink().run()
  } else if ((label && label !== originalText.trim()) || range.from === range.to) {
    // New wording (or nothing selected): replace the range with the text, linked.
    e.chain().focus().insertContentAt(range, {
      type: 'text', text: label || href, marks: [{ type: 'link', attrs: { href } }],
    }).run()
  } else {
    e.chain().focus().setTextSelection(range).extendMarkRange('link').setLink({ href }).run()
  }
  open.value = false
}

function toFile() {
  open.value = false
  linkToFile()
}

defineExpose({ show: () => onOpen(true) })

function remove() {
  editor.value?.chain().focus().extendMarkRange('link').unsetLink().run()
  open.value = false
}
</script>

<template>
  <Popover :open @update:open="onOpen">
    <PopoverAnchor v-if="at" as-child>
      <span class="pointer-events-none fixed size-0" :style="{ left: `${at.x}px`, top: `${at.y}px` }" />
    </PopoverAnchor>
    <PopoverTrigger v-else as-child>
      <Button
        size="icon-sm" variant="ghost"
        :title :aria-label="title" :aria-pressed="icon ? undefined : editor?.isActive('link')"
        :class="!icon && editor?.isActive('link') && 'bg-accent text-primary'"
      >
        <component :is="icon ?? LinkIcon" />
      </Button>
    </PopoverTrigger>
    <PopoverContent class="w-96 p-2">
      <p class="mb-2 font-medium text-muted-foreground">{{ t('Link') }}</p>
      <Input v-model="text" :placeholder="t('Link text')" class="mb-2 h-8" :aria-label="t('Link text')"
        @keydown.enter.prevent="apply" />
      <div class="flex gap-2">
        <Input v-model="url" placeholder="https://…" class="h-8 flex-1" :aria-label="t('Link URL')" @keydown.enter.prevent="apply" />
        <Button size="sm" @click="apply">OK</Button>
        <Button
          v-if="editor?.isActive('link')" size="icon-sm" variant="ghost" class="text-destructive hover:text-destructive"
          :title="t('Remove link')" :aria-label="t('Remove link')" @click="remove"
        >
          <Link2Off />
        </Button>
      </div>
      <Button variant="ghost" size="sm" class="mt-1 w-full justify-start" @click="toFile">
        <FileSymlink />{{ t('Link to a file…') }}
      </Button>
    </PopoverContent>
  </Popover>
</template>
