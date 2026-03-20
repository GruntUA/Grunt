<script setup lang="ts">
import { onBeforeUnmount, watch } from 'vue'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Link from '@tiptap/extension-link'
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
</script>

<template>
  <div class="flex flex-col gap-1">
    <label class="text-sm font-medium text-[--grunt-text-primary]">
      {{ field.label }}<span v-if="field.required" class="text-[--grunt-danger] ml-0.5">*</span>
    </label>

    <!-- Toolbar -->
    <div v-if="editor" class="flex gap-1 p-1 border border-[--grunt-border] border-b-0 rounded-t-[--grunt-radius-sm] bg-[--grunt-surface-secondary] flex-wrap">
      <button type="button" class="px-2 py-0.5 text-xs rounded hover:bg-[--grunt-border] transition-colors" :class="{ 'bg-[--grunt-border]': editor.isActive('bold') }" @click="editor.chain().focus().toggleBold().run()"><b>B</b></button>
      <button type="button" class="px-2 py-0.5 text-xs rounded hover:bg-[--grunt-border] transition-colors" :class="{ 'bg-[--grunt-border]': editor.isActive('italic') }" @click="editor.chain().focus().toggleItalic().run()"><i>I</i></button>
      <button type="button" class="px-2 py-0.5 text-xs rounded hover:bg-[--grunt-border] transition-colors" :class="{ 'bg-[--grunt-border]': editor.isActive('strike') }" @click="editor.chain().focus().toggleStrike().run()"><s>S</s></button>
      <div class="w-px bg-[--grunt-border] mx-0.5" />
      <button type="button" class="px-2 py-0.5 text-xs rounded hover:bg-[--grunt-border] transition-colors" :class="{ 'bg-[--grunt-border]': editor.isActive('heading', { level: 2 }) }" @click="editor.chain().focus().toggleHeading({ level: 2 }).run()">H2</button>
      <button type="button" class="px-2 py-0.5 text-xs rounded hover:bg-[--grunt-border] transition-colors" :class="{ 'bg-[--grunt-border]': editor.isActive('heading', { level: 3 }) }" @click="editor.chain().focus().toggleHeading({ level: 3 }).run()">H3</button>
      <div class="w-px bg-[--grunt-border] mx-0.5" />
      <button type="button" class="px-2 py-0.5 text-xs rounded hover:bg-[--grunt-border] transition-colors" :class="{ 'bg-[--grunt-border]': editor.isActive('bulletList') }" @click="editor.chain().focus().toggleBulletList().run()">• List</button>
      <button type="button" class="px-2 py-0.5 text-xs rounded hover:bg-[--grunt-border] transition-colors" :class="{ 'bg-[--grunt-border]': editor.isActive('orderedList') }" @click="editor.chain().focus().toggleOrderedList().run()">1. List</button>
    </div>

    <div
      class="border border-[--grunt-border] rounded-b-[--grunt-radius-sm] min-h-[120px] focus-within:ring-2 focus-within:ring-[--grunt-primary]/30 focus-within:border-[--grunt-primary]"
      :class="{ 'border-[--grunt-danger]': error }"
    >
      <EditorContent :editor="editor" class="prose prose-sm max-w-none p-3 text-sm" />
    </div>

    <p v-if="error" class="text-xs text-[--grunt-danger]">{{ error }}</p>
    <p v-else-if="field.description" class="text-xs text-[--grunt-text-muted]">{{ field.description }}</p>
  </div>
</template>
