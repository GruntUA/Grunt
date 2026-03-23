<script setup lang="ts">
import { onBeforeUnmount, watch } from 'vue'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Link from '@tiptap/extension-link'
import { Toggle } from '@/components/ui/toggle'
import { Separator } from '@/components/ui/separator'
import {
  Bold,
  Italic,
  Strikethrough,
  Heading2,
  Heading3,
  List,
  ListOrdered,
  Quote,
  Undo,
  Redo,
  Code,
  Link as LinkIcon,
} from 'lucide-vue-next'
import type { DocField } from '@/types'

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const editor = useEditor({
  content: String(props.modelValue ?? ''),
  editable: !props.disabled && !props.field.read_only,
  extensions: [
    StarterKit,
    Link.configure({ openOnClick: false }),
  ],
  onUpdate: ({ editor }) => {
    emit('update:modelValue', editor.getHTML())
  },
})

watch(() => props.disabled, (v) => editor.value?.setEditable(!v))
watch(() => props.modelValue, (v) => {
  const html = String(v ?? '')
  if (editor.value && editor.value.getHTML() !== html) {
    editor.value.commands.setContent(html, false)
  }
})

onBeforeUnmount(() => editor.value?.destroy())

function setLink() {
  if (!editor.value) return
  const url = window.prompt('URL')
  if (url) {
    editor.value.chain().focus().setLink({ href: url }).run()
  }
}
</script>

<template>
  <div class="flex flex-col gap-1.5">
    <!-- Toolbar -->
    <div v-if="editor" class="flex items-center gap-0.5 rounded-t-md border border-b-0 border-input bg-muted/50 p-1 flex-wrap">
      <Toggle size="sm" :pressed="editor.isActive('bold')" @click="editor.chain().focus().toggleBold().run()">
        <Bold class="size-4" />
      </Toggle>
      <Toggle size="sm" :pressed="editor.isActive('italic')" @click="editor.chain().focus().toggleItalic().run()">
        <Italic class="size-4" />
      </Toggle>
      <Toggle size="sm" :pressed="editor.isActive('strike')" @click="editor.chain().focus().toggleStrike().run()">
        <Strikethrough class="size-4" />
      </Toggle>
      <Toggle size="sm" :pressed="editor.isActive('code')" @click="editor.chain().focus().toggleCode().run()">
        <Code class="size-4" />
      </Toggle>

      <Separator orientation="vertical" class="mx-1 h-6" />

      <Toggle size="sm" :pressed="editor.isActive('heading', { level: 2 })" @click="editor.chain().focus().toggleHeading({ level: 2 }).run()">
        <Heading2 class="size-4" />
      </Toggle>
      <Toggle size="sm" :pressed="editor.isActive('heading', { level: 3 })" @click="editor.chain().focus().toggleHeading({ level: 3 }).run()">
        <Heading3 class="size-4" />
      </Toggle>

      <Separator orientation="vertical" class="mx-1 h-6" />

      <Toggle size="sm" :pressed="editor.isActive('bulletList')" @click="editor.chain().focus().toggleBulletList().run()">
        <List class="size-4" />
      </Toggle>
      <Toggle size="sm" :pressed="editor.isActive('orderedList')" @click="editor.chain().focus().toggleOrderedList().run()">
        <ListOrdered class="size-4" />
      </Toggle>
      <Toggle size="sm" :pressed="editor.isActive('blockquote')" @click="editor.chain().focus().toggleBlockquote().run()">
        <Quote class="size-4" />
      </Toggle>

      <Separator orientation="vertical" class="mx-1 h-6" />

      <Toggle size="sm" :pressed="editor.isActive('link')" @click="setLink">
        <LinkIcon class="size-4" />
      </Toggle>

      <div class="flex-1" />

      <Toggle size="sm" :pressed="false" @click="editor.chain().focus().undo().run()" :disabled="!editor.can().undo()">
        <Undo class="size-4" />
      </Toggle>
      <Toggle size="sm" :pressed="false" @click="editor.chain().focus().redo().run()" :disabled="!editor.can().redo()">
        <Redo class="size-4" />
      </Toggle>
    </div>

    <div
      class="rounded-b-md border border-input min-h-[120px] focus-within:ring-1 focus-within:ring-ring focus-within:border-ring transition-colors"
      :class="{ 'border-destructive focus-within:ring-destructive': error }"
    >
      <EditorContent :editor="editor" class="prose prose-sm max-w-none p-3 text-sm text-foreground" />
    </div>

    <p v-if="error" class="text-xs text-destructive">{{ error }}</p>
    <p v-else-if="field.description" class="text-xs text-muted-foreground">{{ field.description }}</p>
  </div>
</template>
