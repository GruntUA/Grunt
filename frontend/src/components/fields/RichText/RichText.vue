<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { EditorContent } from '@tiptap/vue-3'
// Geist is the editor typeface only - loaded with this (lazy) chunk, not app-wide.
import '@fontsource-variable/geist'
import type { DocField } from '@/types'
import type { AttachmentResult } from '@/components/fields/Attach/attachment'
import AttachPicker from '@/components/fields/Attach/AttachPicker.vue'
import { provideRichEditor, useRichEditor } from './editor/useRichEditor'
import { useFullscreen } from './editor/useFullscreen'
import EditorToolbar from './ui/EditorToolbar.vue'
import EditorContextMenu from './ui/EditorContextMenu.vue'
import LinkBubble from './ui/LinkBubble.vue'
import ImageBubble from './ui/ImageBubble.vue'
import BlockHandle from './ui/BlockHandle.vue'
import SlashMenu from './ui/SlashMenu.vue'
import './content.css'

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
  maxLength?: number
  placeholder?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const { t } = useI18n()

const rich = useRichEditor(props, (_, v) => emit('update:modelValue', v))
provideRichEditor(rich)
const { editor, editable, maxLength, picker, onPicked } = rich

const documentStyle = props.field.options === 'document'
const fullscreen = useFullscreen(() => editor.value?.commands.focus())

const characters = () => editor.value?.storage.characterCount.characters() ?? 0
const words = () => editor.value?.storage.characterCount.words() ?? 0
</script>

<template>
  <div>
    <!-- Full screen moves the editor to <body> so it can cover the whole page. -->
    <Teleport to="body" :disabled="!fullscreen">
      <div
        data-richtext class="flex flex-col gap-1.5"
        :class="fullscreen && 'fixed inset-0 z-50 overflow-y-auto bg-background px-4 pb-4 sm:px-[max(1rem,calc(50vw-32rem))]'"
      >
        <EditorToolbar v-if="editor && editable()" v-model:fullscreen="fullscreen" :document-style />

        <div
          class="relative border border-border transition-colors focus-within:border-primary focus-within:ring-1 focus-within:ring-primary"
          :class="[
            editable() ? 'rounded-b-md' : 'rounded-md bg-muted/30',
            error && '!border-destructive focus-within:!ring-destructive',
            fullscreen ? 'min-h-[calc(100svh-6rem)] bg-card' : 'min-h-[120px]',
          ]"
        >
          <LinkBubble />
          <ImageBubble />
          <BlockHandle v-if="editable()" />
          <EditorContextMenu>
            <EditorContent
              :editor class="richtext-content py-3 pr-3 text-foreground"
              :class="[documentStyle && 'richtext-document', editable() ? 'pl-8' : 'pl-3']"
            />
          </EditorContextMenu>
        </div>

        <!-- Error is rendered by FieldRenderer -->
        <p v-if="editor" class="self-end text-muted-foreground tabular-nums" aria-live="off">
          <template v-if="maxLength()">{{ characters() }} / {{ maxLength() }}</template>
          <template v-else>{{ t('{words} w · {chars} ch', { words: words(), chars: characters() }) }}</template>
        </p>

        <SlashMenu />
        <AttachPicker
          :open="!!picker"
          :image-only="picker?.kind === 'gallery'"
          :multiple="picker?.kind !== 'link'"
          :current-url="picker?.currentUrl"
          :title="picker?.kind === 'link' ? t('Link to a file') : undefined"
          :action-label="picker?.kind === 'link' ? t('Insert link') : undefined"
          @update:open="(open: boolean) => { if (!open) onPicked([]) }"
          @select="(r: AttachmentResult) => onPicked([r])"
          @select-many="onPicked"
        />
      </div>
    </Teleport>
  </div>
</template>
