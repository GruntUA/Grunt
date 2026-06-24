<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import { Extension } from '@tiptap/core'
import type { EditorState, Transaction } from '@tiptap/pm/state'
import type { Node as PmNode } from '@tiptap/pm/model'
import StarterKit from '@tiptap/starter-kit'
import { TextStyle } from '@tiptap/extension-text-style'
import Link from '@tiptap/extension-link'
import Image from '@tiptap/extension-image'
import Placeholder from '@tiptap/extension-placeholder'
import CharacterCount from '@tiptap/extension-character-count'
import { TableKit } from '@tiptap/extension-table'

import {
  Bold, Italic, Strikethrough,
  Heading2, Heading3,
  List, ListOrdered,
  Quote, Undo, Redo,
  Code, Code2,
  Link as LinkIcon, Link2Off,
  Minus, Image as ImageIcon,
  Table as TableIcon,
  Upload, IndentIncrease, IndentDecrease,
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

// ── Font & Indent data ────────────────────────────────────────────────────────
const FONT_FAMILIES = [
  { label: 'За замовчуванням', value: '' },
  { label: 'Arial', value: 'Arial, sans-serif' },
  { label: 'Georgia', value: 'Georgia, serif' },
  { label: 'Times New Roman', value: '"Times New Roman", serif' },
  { label: 'Courier New', value: '"Courier New", monospace' },
  { label: 'Verdana', value: 'Verdana, sans-serif' },
]

const FONT_SIZES = [
  { label: 'Авто', value: '' },
  { label: '10', value: '10px' },
  { label: '12', value: '12px' },
  { label: '14', value: '14px' },
  { label: '16', value: '16px' },
  { label: '18', value: '18px' },
  { label: '20', value: '20px' },
  { label: '24', value: '24px' },
  { label: '28', value: '28px' },
  { label: '36', value: '36px' },
  { label: '48', value: '48px' },
]

const currentFontFamily = ref<string>('')
const currentFontSize = ref<string>('')

function updateFormatState() {
  if (!editor.value) return
  const attrs = editor.value.getAttributes('textStyle')
  currentFontFamily.value = attrs.fontFamily ?? ''
  currentFontSize.value = attrs.fontSize ?? ''
}

function applyFontFamily(val: string) {
  if (!editor.value) return
  const cur = editor.value.getAttributes('textStyle') ?? {}
  const attrs = { ...cur, fontFamily: val || null }
  editor.value.chain().focus().setMark('textStyle', attrs).run()
  if (!val) editor.value.chain().focus().removeEmptyTextStyle().run()
  currentFontFamily.value = val
}

function applyFontSize(val: string) {
  if (!editor.value) return
  const cur = editor.value.getAttributes('textStyle') ?? {}
  const attrs = { ...cur, fontSize: val || null }
  editor.value.chain().focus().setMark('textStyle', attrs).run()
  if (!val) editor.value.chain().focus().removeEmptyTextStyle().run()
  currentFontSize.value = val
}

// ── Custom TextStyle with fontFamily + fontSize ───────────────────────────────
const RichTextStyle = TextStyle.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      fontFamily: {
        default: null,
        parseHTML: (el: HTMLElement) => el.style.fontFamily?.replace(/['"]+/g, '') || null,
        renderHTML: (attrs: Record<string, any>) => attrs.fontFamily ? { style: `font-family: ${attrs.fontFamily}` } : {},
      },
      fontSize: {
        default: null,
        parseHTML: (el: HTMLElement) => el.style.fontSize || null,
        renderHTML: (attrs: Record<string, any>) => attrs.fontSize ? { style: `font-size: ${attrs.fontSize}` } : {},
      },
    }
  },
})

// ── Indent extension ──────────────────────────────────────────────────────────
const INDENT_STEP = 40
const MAX_INDENT = 7
const INDENT_TYPES = ['paragraph', 'heading', 'blockquote']

const IndentExt = Extension.create({
  name: 'indent',
  addGlobalAttributes() {
    return [{
      types: INDENT_TYPES,
      attributes: {
        indent: {
          default: 0,
          parseHTML: el => {
            const v = parseInt(el.style.marginLeft || '0')
            return v ? Math.round(v / INDENT_STEP) : 0
          },
          renderHTML: attrs => attrs.indent > 0
            ? { style: `margin-left: ${attrs.indent * INDENT_STEP}px` }
            : {},
        },
      },
    }]
  },
  addCommands() {
    return {
      indent: () => ({ state, dispatch }: { state: EditorState; dispatch: ((tr: Transaction) => void) | undefined }) => {
        const { selection } = state
        const tr = state.tr
        state.doc.nodesBetween(selection.from, selection.to, (node: PmNode, pos: number) => {
          if (INDENT_TYPES.includes(node.type.name))
            tr.setNodeMarkup(pos, undefined, {
              ...node.attrs,
              indent: Math.min((node.attrs.indent || 0) + 1, MAX_INDENT),
            })
        })
        if (dispatch) dispatch(tr)
        return true
      },
      outdent: () => ({ state, dispatch }: { state: EditorState; dispatch: ((tr: Transaction) => void) | undefined }) => {
        const { selection } = state
        const tr = state.tr
        state.doc.nodesBetween(selection.from, selection.to, (node: PmNode, pos: number) => {
          if (INDENT_TYPES.includes(node.type.name))
            tr.setNodeMarkup(pos, undefined, {
              ...node.attrs,
              indent: Math.max((node.attrs.indent || 0) - 1, 0),
            })
        })
        if (dispatch) dispatch(tr)
        return true
      },
    } as any
  },
  addKeyboardShortcuts() {
    return {
      Tab: () => {
        if (this.editor.isActive('listItem')) return false
        return (this.editor.commands as any).indent()
      },
      'Shift-Tab': () => {
        if (this.editor.isActive('listItem')) return false
        return (this.editor.commands as any).outdent()
      },
    }
  },
})

// ── Bubble menu ───────────────────────────────────────────────────────────────
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

// ── Link popover ──────────────────────────────────────────────────────────────
const op = ref<any>(null);
const linkUrl  = ref('')

function openLinkPopover(event: any) {
  if (!editor.value) return
  linkUrl.value = editor.value.getAttributes('link').href ?? ''
  op.value.toggle(event);
}

function applyLink() {
  if (!editor.value) return
  const url = linkUrl.value.trim()
  url
    ? editor.value.chain().focus().extendMarkRange('link').setLink({ href: url }).run()
    : editor.value.chain().focus().extendMarkRange('link').unsetLink().run()
  op.value.hide();
}

function removeLink() {
  editor.value?.chain().focus().extendMarkRange('link').unsetLink().run()
  op.value.hide();
}

// ── Image ─────────────────────────────────────────────────────────────────────
const opImage = ref<any>(null);
const imageUrl       = ref('')
const imageUploading = ref(false)

function openImagePopover(event: any) {
    opImage.value.toggle(event);
}

function insertImageUrl() {
  const url = imageUrl.value.trim()
  if (url) editor.value?.chain().focus().setImage({ src: url }).run()
  imageUrl.value = ''
  opImage.value.hide();
}

async function uploadImage(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  imageUploading.value = true
  try {
    const item = await filesApi.upload(file)
    editor.value?.chain().focus().setImage({ src: item.url, alt: item.filename }).run()
    opImage.value.hide();
  } finally {
    imageUploading.value = false
  }
}

// ── Editor ────────────────────────────────────────────────────────────────────
const editor = useEditor({
  content: String(props.modelValue ?? ''),
  editable: isEditable(),
  extensions: [
    StarterKit.configure({
      link: false,
    }),
    RichTextStyle,
    IndentExt,
    Link.configure({ openOnClick: false }),
    Image.configure({ inline: false }),
    TableKit,
    Placeholder.configure({ placeholder: props.placeholder ?? props.field.label ?? '' }),
    CharacterCount.configure(props.maxLength ? { limit: props.maxLength } : {}),
  ],
  onUpdate: ({ editor: e }) => { emit('update:modelValue', e.getHTML()); updateFormatState() },
  onSelectionUpdate: () => { updateBubble(); updateFormatState() },
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

const doIndent  = () => (editor.value?.commands as any)?.indent?.()
const doOutdent = () => (editor.value?.commands as any)?.outdent?.()
</script>

<template>
  <div class="flex flex-col gap-1.5">

    <!-- ── Toolbar ────────────────────────────────────────────────────── -->
    <div
      v-if="editor && isEditable()"
      class="flex items-center gap-0.5 rounded-t-md border border-b-0 border-border bg-muted/50 p-1 flex-wrap text-foreground"
    >
      <!-- Font family -->
      <Select
        :model-value="currentFontFamily"
        :options="FONT_FAMILIES"
        option-label="label"
        option-value="value"
        size="small"
        class="h-7 w-36 text-xs"
        @change="applyFontFamily(($event as any).value)"
      />
      <!-- Font size -->
      <Select
        :model-value="currentFontSize"
        :options="FONT_SIZES"
        option-label="label"
        option-value="value"
        size="small"
        class="h-7 w-[4.5rem] text-xs"
        @change="applyFontSize(($event as any).value)"
      />

      <Divider layout="vertical" class="!mx-1 !h-6 !my-0" />

      <Button size="small" :severity="editor.isActive('bold') ? 'primary' : 'secondary'" variant="text"
        :disabled="!editor.can().chain().focus().toggleBold().run()"
        @click="editor.chain().focus().toggleBold().run()">
        <Bold class="size-4" />
      </Button>
      <Button size="small" :severity="editor.isActive('italic') ? 'primary' : 'secondary'" variant="text"
        :disabled="!editor.can().chain().focus().toggleItalic().run()"
        @click="editor.chain().focus().toggleItalic().run()">
        <Italic class="size-4" />
      </Button>
      <Button size="small" :severity="editor.isActive('strike') ? 'primary' : 'secondary'" variant="text"
        :disabled="!editor.can().chain().focus().toggleStrike().run()"
        @click="editor.chain().focus().toggleStrike().run()">
        <Strikethrough class="size-4" />
      </Button>
      <Button size="small" :severity="editor.isActive('code') ? 'primary' : 'secondary'" variant="text"
        :disabled="!editor.can().chain().focus().toggleCode().run()"
        @click="editor.chain().focus().toggleCode().run()">
        <Code class="size-4" />
      </Button>

      <Divider layout="vertical" class="!mx-1 !h-6 !my-0" />

      <Button size="small" :severity="editor.isActive('heading', { level: 2 }) ? 'primary' : 'secondary'" variant="text"
        @click="editor.chain().focus().toggleHeading({ level: 2 }).run()">
        <Heading2 class="size-4" />
      </Button>
      <Button size="small" :severity="editor.isActive('heading', { level: 3 }) ? 'primary' : 'secondary'" variant="text"
        @click="editor.chain().focus().toggleHeading({ level: 3 }).run()">
        <Heading3 class="size-4" />
      </Button>

      <Divider layout="vertical" class="!mx-1 !h-6 !my-0" />

      <Button size="small" :severity="editor.isActive('bulletList') ? 'primary' : 'secondary'" variant="text"
        @click="editor.chain().focus().toggleBulletList().run()">
        <List class="size-4" />
      </Button>
      <Button size="small" :severity="editor.isActive('orderedList') ? 'primary' : 'secondary'" variant="text"
        @click="editor.chain().focus().toggleOrderedList().run()">
        <ListOrdered class="size-4" />
      </Button>
      <Button size="small" :severity="editor.isActive('blockquote') ? 'primary' : 'secondary'" variant="text"
        @click="editor.chain().focus().toggleBlockquote().run()">
        <Quote class="size-4" />
      </Button>

      <!-- Indent / Outdent -->
      <Button size="small" severity="secondary" variant="text" @click="doIndent">
        <IndentIncrease class="size-4" />
      </Button>
      <Button size="small" severity="secondary" variant="text" @click="doOutdent">
        <IndentDecrease class="size-4" />
      </Button>

      <Button size="small" :severity="editor.isActive('codeBlock') ? 'primary' : 'secondary'" variant="text"
        @click="editor.chain().focus().toggleCodeBlock().run()">
        <Code2 class="size-4" />
      </Button>
      <Button size="small" severity="secondary" variant="text"
        @click="editor.chain().focus().setHorizontalRule().run()">
        <Minus class="size-4" />
      </Button>

      <Divider layout="vertical" class="!mx-1 !h-6 !my-0" />

      <!-- Link -->
      <Button size="small" :severity="editor.isActive('link') ? 'primary' : 'secondary'" variant="text" @click="openLinkPopover">
        <LinkIcon class="size-4" />
      </Button>
      <Popover ref="op">
          <div class="w-72 p-1">
              <p class="text-xs font-medium text-muted-foreground mb-2">Посилання</p>
              <div class="flex gap-2">
                <InputText v-model="linkUrl" placeholder="https://…" class="h-8 text-sm flex-1"
                  @keydown.enter.prevent="applyLink" />
                <Button size="small" class="h-8 px-3" @click="applyLink">OK</Button>
                <Button v-if="editor.isActive('link')" severity="danger" size="small" variant="text" class="h-8 px-2" @click="removeLink">
                  <Link2Off class="size-4" />
                </Button>
              </div>
          </div>
      </Popover>

      <!-- Image -->
      <Button size="small" severity="secondary" variant="text" @click="openImagePopover">
        <ImageIcon class="size-4" />
      </Button>
      <Popover ref="opImage">
          <div class="w-72 p-1">
              <p class="text-xs font-medium text-muted-foreground mb-2">Зображення</p>
              <div class="flex gap-2 mb-2">
                <InputText v-model="imageUrl" placeholder="https://…" class="h-8 text-sm flex-1"
                  @keydown.enter.prevent="insertImageUrl" />
                <Button size="small" class="h-8 px-3" @click="insertImageUrl">OK</Button>
              </div>
              <label class="flex items-center gap-2 cursor-pointer text-xs text-muted-foreground hover:text-foreground transition-colors p-2 hover:bg-muted rounded">
                <Upload class="size-3.5" />
                <span>{{ imageUploading ? 'Завантаження…' : 'Завантажити файл' }}</span>
                <input type="file" accept="image/*" class="hidden" :disabled="imageUploading" @change="uploadImage" />
              </label>
          </div>
      </Popover>

      <!-- Table -->
      <Button size="small" :severity="editor.isActive('table') ? 'primary' : 'secondary'" variant="text"
        @click="editor.isActive('table')
          ? editor.chain().focus().deleteTable().run()
          : editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()">
        <TableIcon class="size-4" />
      </Button>

      <div class="flex-1" />

      <Button size="small" severity="secondary" variant="text"
        :disabled="!editor.can().chain().focus().undo().run()"
        @click="editor.chain().focus().undo().run()">
        <Undo class="size-4" />
      </Button>
      <Button size="small" severity="secondary" variant="text"
        :disabled="!editor.can().chain().focus().redo().run()"
        @click="editor.chain().focus().redo().run()">
        <Redo class="size-4" />
      </Button>
    </div>

    <!-- ── Editor area ─────────────────────────────────────────────────── -->
    <div
      ref="wrapperEl"
      class="relative border border-border min-h-[120px] focus-within:ring-1 focus-within:ring-primary focus-within:border-primary transition-colors"
      :class="[
        isEditable() ? 'rounded-b-md' : 'rounded-md',
        error ? '!border-destructive focus-within:!ring-destructive' : '',
        !isEditable() ? 'bg-muted/30' : '',
      ]"
    >
      <!-- Bubble menu -->
      <Transition name="bubble">
        <div
          v-if="bubbleVisible && isEditable()"
          :style="bubbleStyle"
          class="absolute z-20 flex items-center gap-0.5 rounded-md border border-border bg-background/95 backdrop-blur-sm shadow-md p-1 text-foreground pointer-events-auto"
        >
          <Button size="small" :severity="editor!.isActive('bold') ? 'primary' : 'secondary'" variant="text"
            @click="editor!.chain().focus().toggleBold().run()">
            <Bold class="size-3.5" />
          </Button>
          <Button size="small" :severity="editor!.isActive('italic') ? 'primary' : 'secondary'" variant="text"
            @click="editor!.chain().focus().toggleItalic().run()">
            <Italic class="size-3.5" />
          </Button>
          <Button size="small" :severity="editor!.isActive('strike') ? 'primary' : 'secondary'" variant="text"
            @click="editor!.chain().focus().toggleStrike().run()">
            <Strikethrough class="size-3.5" />
          </Button>
          <Divider layout="vertical" class="!mx-0.5 !h-5 !my-0" />
          <Button size="small" :severity="editor!.isActive('link') ? 'primary' : 'secondary'" variant="text" @click="openLinkPopover">
            <LinkIcon class="size-3.5" />
          </Button>
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
  color: var(--p-text-muted-color);
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
  background-color: var(--p-content-background);
  border-radius: 0.3rem;
  font-size: 0.85em;
  padding: 0.2em 0.4em;
  font-family: ui-monospace, monospace;
}
.richtext-content .tiptap pre {
  background: #0f172a;
  color: #f8fafc;
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
  border-left: 3px solid var(--p-content-border-color);
  margin: 0.75rem 0;
  padding-left: 1rem;
  color: var(--p-text-muted-color);
}
.richtext-content .tiptap hr {
  border: none;
  border-top: 1px solid var(--p-content-border-color);
  margin: 1.25rem 0;
}
.richtext-content .tiptap a {
  color: var(--p-primary-color);
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
  outline: 2px solid var(--p-primary-color);
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
  border: 1px solid var(--p-content-border-color);
  padding: 0.4rem 0.6rem;
  vertical-align: top;
  min-width: 80px;
  position: relative;
}
.richtext-content .tiptap th {
  background-color: var(--p-content-background);
  font-weight: 600;
}
.richtext-content .tiptap .selectedCell::after {
  content: '';
  position: absolute;
  inset: 0;
  background: var(--p-primary-color);
  opacity: 0.1;
  pointer-events: none;
}
.richtext-content .tiptap .column-resize-handle {
  position: absolute;
  right: -2px;
  top: 0; bottom: 0;
  width: 4px;
  background-color: var(--p-primary-color);
  cursor: col-resize;
  pointer-events: all;
}
.richtext-content .tiptap .tableWrapper { overflow-x: auto; }

/* Bubble menu transition */
.bubble-enter-active, .bubble-leave-active { transition: opacity 0.12s, transform 0.12s; }
.bubble-enter-from, .bubble-leave-to { opacity: 0; transform: translateY(4px); }
</style>
