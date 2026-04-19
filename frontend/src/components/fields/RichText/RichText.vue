<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Link from '@tiptap/extension-link'
import Image from '@tiptap/extension-image'
import Placeholder from '@tiptap/extension-placeholder'
import CharacterCount from '@tiptap/extension-character-count'
import { TableKit } from '@tiptap/extension-table'

import { Toggle } from '@/components/ui/toggle'
import { Separator } from '@/components/ui/separator'
import Button from 'primevue/button'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  Bold, Italic, Strikethrough,
  Heading2, Heading3,
  List, ListOrdered,
  Quote, Undo, Redo,
  Code, Code2,
  Link as LinkIcon, Link2Off,
  Minus, Image as ImageIcon,
  Table as TableIcon,
  Upload,
} from '@lucide/vue'
import type { DocField } from '@/types'
import { filesApi } from '@/core/api/files'

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
  maxLength?: number
  placeholder?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const isEditable = () => !props.disabled && !props.field.read_only

// ── Bubble menu ──────────────────────────────────────────────────────────────
const wrapperEl = ref<HTMLElement | null>(null)
const bubbleVisible = ref(false)
const bubbleStyle = ref<Record<string, string>>({})

function updateBubble() {
  if (!editor.value || !wrapperEl.value) return
  const { empty, from } = editor.value.state.selection
  if (empty) { bubbleVisible.value = false; return }
  try {
    const coords = editor.value.view.coordsAtPos(from)
    const rect = wrapperEl.value.getBoundingClientRect()
    bubbleStyle.value = {
      left: `${Math.max(0, coords.left - rect.left)}px`,
      top:  `${coords.top - rect.top - 44}px`,
    }
    bubbleVisible.value = true
  } catch { bubbleVisible.value = false }
}

// ── Link popover ─────────────────────────────────────────────────────────────
const linkOpen = ref(false)
const linkUrl  = ref('')

function openLinkPopover() {
  if (!editor.value) return
  linkUrl.value = editor.value.getAttributes('link').href ?? ''
  linkOpen.value = true
}

function applyLink() {
  if (!editor.value) return
  const url = linkUrl.value.trim()
  url
    ? editor.value.chain().focus().extendMarkRange('link').setLink({ href: url }).run()
    : editor.value.chain().focus().extendMarkRange('link').unsetLink().run()
  linkOpen.value = false
}

function removeLink() {
  editor.value?.chain().focus().extendMarkRange('link').unsetLink().run()
  linkOpen.value = false
}

// ── Image ────────────────────────────────────────────────────────────────────
const imageOpen      = ref(false)
const imageUrl       = ref('')
const imageUploading = ref(false)

function insertImageUrl() {
  const url = imageUrl.value.trim()
  if (url) editor.value?.chain().focus().setImage({ src: url }).run()
  imageUrl.value = ''
  imageOpen.value = false
}

async function uploadImage(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  imageUploading.value = true
  try {
    const item = await filesApi.upload(file)
    editor.value?.chain().focus().setImage({ src: item.url, alt: item.filename }).run()
    imageOpen.value = false
  } finally {
    imageUploading.value = false
  }
}

// ── Editor ───────────────────────────────────────────────────────────────────
const editor = useEditor({
  content: String(props.modelValue ?? ''),
  editable: isEditable(),
  extensions: [
    StarterKit,
    Link.configure({ openOnClick: false }),
    Image.configure({ inline: false }),
    TableKit,
    Placeholder.configure({ placeholder: props.placeholder ?? props.field.label ?? '' }),
    CharacterCount.configure(props.maxLength ? { limit: props.maxLength } : {}),
  ],
  onUpdate: ({ editor: e }) => emit('update:modelValue', e.getHTML()),
  onSelectionUpdate: () => updateBubble(),
  onBlur: () => { bubbleVisible.value = false },
})

watch(() => props.disabled,       () => editor.value?.setEditable(isEditable()))
watch(() => props.field.read_only, () => editor.value?.setEditable(isEditable()))
watch(() => props.modelValue, (v) => {
  const html = String(v ?? '')
  if (editor.value && editor.value.getHTML() !== html)
    editor.value.commands.setContent(html, { emitUpdate: false })
})

onBeforeUnmount(() => editor.value?.destroy())

const charCount = () => editor.value?.storage.characterCount.characters() ?? 0
const wordCount = () => editor.value?.storage.characterCount.words() ?? 0
</script>

<template>
  <div class="flex flex-col gap-1.5">

    <!-- ── Toolbar ─────────────────────────────────────────────────────── -->
    <div
      v-if="editor && isEditable()"
      class="flex items-center gap-0.5 rounded-t-md border border-b-0 border-input bg-muted/50 p-1 flex-wrap text-foreground"
    >
      <Toggle size="sm" :pressed="editor.isActive('bold')"
        :disabled="!editor.can().chain().focus().toggleBold().run()"
        @click="editor.chain().focus().toggleBold().run()">
        <Bold class="size-4" />
      </Toggle>
      <Toggle size="sm" :pressed="editor.isActive('italic')"
        :disabled="!editor.can().chain().focus().toggleItalic().run()"
        @click="editor.chain().focus().toggleItalic().run()">
        <Italic class="size-4" />
      </Toggle>
      <Toggle size="sm" :pressed="editor.isActive('strike')"
        :disabled="!editor.can().chain().focus().toggleStrike().run()"
        @click="editor.chain().focus().toggleStrike().run()">
        <Strikethrough class="size-4" />
      </Toggle>
      <Toggle size="sm" :pressed="editor.isActive('code')"
        :disabled="!editor.can().chain().focus().toggleCode().run()"
        @click="editor.chain().focus().toggleCode().run()">
        <Code class="size-4" />
      </Toggle>

      <Separator orientation="vertical" class="mx-1 h-6" />

      <Toggle size="sm" :pressed="editor.isActive('heading', { level: 2 })"
        @click="editor.chain().focus().toggleHeading({ level: 2 }).run()">
        <Heading2 class="size-4" />
      </Toggle>
      <Toggle size="sm" :pressed="editor.isActive('heading', { level: 3 })"
        @click="editor.chain().focus().toggleHeading({ level: 3 }).run()">
        <Heading3 class="size-4" />
      </Toggle>

      <Separator orientation="vertical" class="mx-1 h-6" />

      <Toggle size="sm" :pressed="editor.isActive('bulletList')"
        @click="editor.chain().focus().toggleBulletList().run()">
        <List class="size-4" />
      </Toggle>
      <Toggle size="sm" :pressed="editor.isActive('orderedList')"
        @click="editor.chain().focus().toggleOrderedList().run()">
        <ListOrdered class="size-4" />
      </Toggle>
      <Toggle size="sm" :pressed="editor.isActive('blockquote')"
        @click="editor.chain().focus().toggleBlockquote().run()">
        <Quote class="size-4" />
      </Toggle>
      <Toggle size="sm" :pressed="editor.isActive('codeBlock')"
        @click="editor.chain().focus().toggleCodeBlock().run()">
        <Code2 class="size-4" />
      </Toggle>
      <Toggle size="sm" :pressed="false"
        @click="editor.chain().focus().setHorizontalRule().run()">
        <Minus class="size-4" />
      </Toggle>

      <Separator orientation="vertical" class="mx-1 h-6" />

      <!-- Link -->
      <Popover v-model:open="linkOpen">
        <PopoverTrigger as-child>
          <Toggle size="sm" :pressed="editor.isActive('link')" @click="openLinkPopover">
            <LinkIcon class="size-4" />
          </Toggle>
        </PopoverTrigger>
        <PopoverContent class="w-72 p-3">
          <p class="text-xs font-medium text-muted-foreground mb-2">Посилання</p>
          <div class="flex gap-2">
            <Input v-model="linkUrl" placeholder="https://…" class="h-8 text-sm"
              @keydown.enter.prevent="applyLink" @keydown.escape="linkOpen = false" />
            <Button size="small" class="h-8 px-3" @click="applyLink">OK</Button>
            <Button v-if="editor.isActive('link')" size="small" text class="h-8 px-2" @click="removeLink">
              <Link2Off class="size-4" />
            </Button>
          </div>
        </PopoverContent>
      </Popover>

      <!-- Image -->
      <Popover v-model:open="imageOpen">
        <PopoverTrigger as-child>
          <Toggle size="sm" :pressed="false" @click="imageOpen = true">
            <ImageIcon class="size-4" />
          </Toggle>
        </PopoverTrigger>
        <PopoverContent class="w-72 p-3">
          <p class="text-xs font-medium text-muted-foreground mb-2">Зображення</p>
          <div class="flex gap-2 mb-2">
            <Input v-model="imageUrl" placeholder="https://…" class="h-8 text-sm"
              @keydown.enter.prevent="insertImageUrl" @keydown.escape="imageOpen = false" />
            <Button size="small" class="h-8 px-3" @click="insertImageUrl">OK</Button>
          </div>
          <label class="flex items-center gap-2 cursor-pointer text-xs text-muted-foreground hover:text-foreground transition-colors">
            <Upload class="size-3.5" />
            <span>{{ imageUploading ? 'Завантаження…' : 'Завантажити файл' }}</span>
            <input type="file" accept="image/*" class="hidden" :disabled="imageUploading" @change="uploadImage" />
          </label>
        </PopoverContent>
      </Popover>

      <!-- Table -->
      <Toggle size="sm" :pressed="editor.isActive('table')"
        @click="editor.isActive('table')
          ? editor.chain().focus().deleteTable().run()
          : editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()">
        <TableIcon class="size-4" />
      </Toggle>

      <div class="flex-1" />

      <Toggle size="sm" :pressed="false"
        :disabled="!editor.can().chain().focus().undo().run()"
        @click="editor.chain().focus().undo().run()">
        <Undo class="size-4" />
      </Toggle>
      <Toggle size="sm" :pressed="false"
        :disabled="!editor.can().chain().focus().redo().run()"
        @click="editor.chain().focus().redo().run()">
        <Redo class="size-4" />
      </Toggle>
    </div>

    <!-- ── Editor area ─────────────────────────────────────────────────── -->
    <div
      ref="wrapperEl"
      class="relative border border-input min-h-[120px] focus-within:ring-1 focus-within:ring-ring focus-within:border-ring transition-colors"
      :class="[
        isEditable() ? 'rounded-b-md' : 'rounded-md',
        error ? 'border-destructive focus-within:ring-destructive' : '',
        !isEditable() ? 'bg-muted/30' : '',
      ]"
    >
      <!-- Bubble menu -->
      <Transition name="bubble">
        <div
          v-if="bubbleVisible && isEditable()"
          :style="bubbleStyle"
          class="absolute z-20 flex items-center gap-0.5 rounded-md border border-input bg-background/95 backdrop-blur-sm shadow-md p-1 text-foreground pointer-events-auto"
        >
          <Toggle size="sm" :pressed="editor!.isActive('bold')"
            @click="editor!.chain().focus().toggleBold().run()">
            <Bold class="size-3.5" />
          </Toggle>
          <Toggle size="sm" :pressed="editor!.isActive('italic')"
            @click="editor!.chain().focus().toggleItalic().run()">
            <Italic class="size-3.5" />
          </Toggle>
          <Toggle size="sm" :pressed="editor!.isActive('strike')"
            @click="editor!.chain().focus().toggleStrike().run()">
            <Strikethrough class="size-3.5" />
          </Toggle>
          <Separator orientation="vertical" class="mx-0.5 h-5" />
          <Toggle size="sm" :pressed="editor!.isActive('link')" @click="openLinkPopover">
            <LinkIcon class="size-3.5" />
          </Toggle>
        </div>
      </Transition>

      <EditorContent :editor="editor" class="richtext-content p-3 text-sm text-foreground" />
    </div>

    <!-- ── Footer ─────────────────────────────────────────────────────── -->
    <div class="flex items-center justify-between">
      <p v-if="error" class="text-xs text-destructive">{{ error }}</p>
      <div v-else />
      <p v-if="editor" class="text-xs text-muted-foreground tabular-nums">
        <template v-if="maxLength">{{ charCount() }} / {{ maxLength }}</template>
        <template v-else>{{ wordCount() }} сл. · {{ charCount() }} симв.</template>
      </p>
    </div>

  </div>
</template>

<style>
.richtext-content .tiptap {
  outline: none;
  min-height: 96px;
}
.richtext-content .tiptap > :first-child { margin-top: 0; }

/* Placeholder */
.richtext-content .tiptap p.is-editor-empty:first-child::before {
  content: attr(data-placeholder);
  color: hsl(var(--muted-foreground));
  pointer-events: none;
  float: left;
  height: 0;
}

.richtext-content .tiptap p { margin: 0.25rem 0; }

.richtext-content .tiptap ul,
.richtext-content .tiptap ol {
  padding: 0 1rem;
  margin: 0.5rem 0 0.5rem 0.4rem;
}
.richtext-content .tiptap ul { list-style-type: disc; }
.richtext-content .tiptap ol { list-style-type: decimal; }
.richtext-content .tiptap li p { margin: 0.15em 0; }

.richtext-content .tiptap h1,
.richtext-content .tiptap h2,
.richtext-content .tiptap h3,
.richtext-content .tiptap h4,
.richtext-content .tiptap h5,
.richtext-content .tiptap h6 {
  line-height: 1.2;
  margin-top: 1.25rem;
  margin-bottom: 0.4rem;
  font-weight: 600;
}
.richtext-content .tiptap h1 { font-size: 1.4rem; }
.richtext-content .tiptap h2 { font-size: 1.2rem; }
.richtext-content .tiptap h3 { font-size: 1.1rem; }
.richtext-content .tiptap h4,
.richtext-content .tiptap h5,
.richtext-content .tiptap h6 { font-size: 1rem; }

.richtext-content .tiptap code {
  background-color: hsl(var(--muted));
  border-radius: 0.3rem;
  font-size: 0.85em;
  padding: 0.2em 0.4em;
  font-family: ui-monospace, monospace;
}
.richtext-content .tiptap pre {
  background: hsl(222 47% 11%);
  color: hsl(210 40% 96%);
  border-radius: 0.5rem;
  margin: 0.75rem 0;
  padding: 0.75rem 1rem;
  font-family: ui-monospace, monospace;
  overflow-x: auto;
}
.richtext-content .tiptap pre code {
  background: none;
  color: inherit;
  font-size: 0.85em;
  padding: 0;
}

.richtext-content .tiptap blockquote {
  border-left: 3px solid hsl(var(--border));
  margin: 0.75rem 0;
  padding-left: 1rem;
  color: hsl(var(--muted-foreground));
}
.richtext-content .tiptap hr {
  border: none;
  border-top: 1px solid hsl(var(--border));
  margin: 1.25rem 0;
}
.richtext-content .tiptap a {
  color: hsl(var(--primary));
  text-decoration: underline;
  cursor: pointer;
}
.richtext-content .tiptap img {
  max-width: 100%;
  height: auto;
  border-radius: 0.375rem;
  margin: 0.5rem 0;
}
.richtext-content .tiptap img.ProseMirror-selectednode {
  outline: 2px solid hsl(var(--primary));
  outline-offset: 2px;
}

/* Tables */
.richtext-content .tiptap table {
  border-collapse: collapse;
  width: 100%;
  margin: 0.75rem 0;
  font-size: 0.875em;
}
.richtext-content .tiptap td,
.richtext-content .tiptap th {
  border: 1px solid hsl(var(--border));
  padding: 0.4rem 0.6rem;
  vertical-align: top;
  min-width: 80px;
  position: relative;
}
.richtext-content .tiptap th {
  background-color: hsl(var(--muted));
  font-weight: 600;
}
.richtext-content .tiptap .selectedCell::after {
  content: '';
  position: absolute;
  inset: 0;
  background: hsl(var(--primary) / 0.1);
  pointer-events: none;
}
.richtext-content .tiptap .column-resize-handle {
  position: absolute;
  right: -2px;
  top: 0; bottom: 0;
  width: 4px;
  background-color: hsl(var(--primary));
  cursor: col-resize;
  pointer-events: all;
}
.richtext-content .tiptap .tableWrapper { overflow-x: auto; }

/* Bubble menu transition */
.bubble-enter-active, .bubble-leave-active { transition: opacity 0.12s, transform 0.12s; }
.bubble-enter-from, .bubble-leave-to { opacity: 0; transform: translateY(4px); }
</style>
