<script setup lang="ts">
import { computed, inject, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import { Extension } from '@tiptap/core'
import type { EditorState, Transaction } from '@tiptap/pm/state'
import type { Node as PmNode } from '@tiptap/pm/model'
import StarterKit from '@tiptap/starter-kit'
import { TextStyle } from '@tiptap/extension-text-style'
import Link from '@tiptap/extension-link'
import TextAlign from '@tiptap/extension-text-align'
import Image from '@tiptap/extension-image'
import Placeholder from '@tiptap/extension-placeholder'
import CharacterCount from '@tiptap/extension-character-count'
import { TableKit } from '@tiptap/extension-table'
import Youtube from '@tiptap/extension-youtube'
// Geist is the editor typeface only — loaded with this (lazy) chunk, not app-wide.
import '@fontsource-variable/geist'
// `mammoth` (~200 kB, pulls jszip) is loaded on demand in importDocx() only.

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
  TextAlignStart, TextAlignCenter, TextAlignEnd, TextAlignJustify,
  FileUp, Loader2, Paperclip, Images, Video, Trash2,
} from '@lucide/vue'
import type { DocField } from '@/types'
import { filesApi } from '@/core/api/files'
import type { AttachmentResult } from '@/core/attachmentChannels/types'
import AttachPicker from '@/components/fields/Attach/AttachPicker.vue'
import type { DocContext } from '@/components/fields/Attach/useAttachmentField'
import { FileList, Gallery, toFileEntry, toGalleryEntry, type FileBlockKind } from './fileBlocks'
import { useToast } from '@/core/composables/useToast'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Popover, PopoverAnchor, PopoverContent } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'

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

const isEditable = () => !props.disabled && !props.field.read_only
const isDocumentStyle = props.field.options === 'document'
const toast = useToast()

// Uploads made here are pending attachments of this DocType; the document
// claims the ones its text refers to when saved (grunt.storage.references).
const docContext = inject<DocContext | null>('docContext', null)
const uploadTarget = () => ({
  attachedToDoctype: docContext?.doctype,
  attachedToId: docContext?.getId() ?? undefined,
})

// FieldRenderer only passes `field` / `modelValue` / `disabled` / `error`, so
// the character limit and placeholder come from field metadata (the explicit
// props stay as an override for direct usage).
const maxLen = computed(() => props.maxLength ?? props.field.max_length)
const placeholderText = computed(() => props.placeholder ?? props.field.placeholder ?? '')

// ── Font & Indent data ────────────────────────────────────────────────────────
// Reka-ui's Select reserves the empty string for "no selection" internally, so
// SelectItem can't use value="" for the placeholder/default entry — a sentinel
// stands in for it and gets translated back to "" at the apply/read boundary.
const FONT_DEFAULT = '__default__'

const STATIC_FONT_FAMILIES = [
  { label: 'Arial', value: 'Arial, sans-serif' },
  { label: 'Georgia', value: 'Georgia, serif' },
  { label: 'Times New Roman', value: '"Times New Roman", serif' },
  { label: 'Courier New', value: '"Courier New", monospace' },
  { label: 'Verdana', value: 'Verdana, sans-serif' },
]

// Document style targets print (the OutgoingLetter format lays the body out in
// pt), so its size presets are in pt — «14» means 14pt, as in Word. Inline /
// web rich text keeps px.
const FONT_SIZE_UNIT = isDocumentStyle ? 'pt' : 'px'
const STATIC_FONT_SIZES = [10, 12, 14, 16, 18, 20, 24, 28, 36, 48].map((n) => ({
  label: String(n),
  value: `${n}${FONT_SIZE_UNIT}`,
}))

const currentFontFamily = ref<string>(FONT_DEFAULT)
const currentFontSize = ref<string>(FONT_DEFAULT)

const FONT_FAMILIES = [
  { label: t('Default'), value: FONT_DEFAULT },
  ...STATIC_FONT_FAMILIES,
]

const FONT_SIZES = [
  { label: t('Auto'), value: FONT_DEFAULT },
  ...STATIC_FONT_SIZES,
]

function nodeAtCursor(): HTMLElement | null {
  if (!editor.value) return null
  try {
    const { node, offset } = editor.value.view.domAtPos(editor.value.state.selection.from)
    const el = node.nodeType === Node.TEXT_NODE ? node.parentElement : (node.childNodes[offset] as Node | undefined) ?? node
    return (el && el.nodeType === Node.ELEMENT_NODE ? el as HTMLElement : (el as ChildNode)?.parentElement) ?? null
  } catch {
    return null
  }
}

function updateFormatState() {
  if (!editor.value) return
  const attrs = editor.value.getAttributes('textStyle')

  const el = nodeAtCursor()
  let effFamily = ''
  let effSize = ''
  if (el) {
    const cs = getComputedStyle(el)
    effFamily = cs.fontFamily.split(',')[0]?.trim().replace(/^["']|["']$/g, '') || ''
    // getComputedStyle always reports px; document presets are pt, so convert
    // before matching a preset label.
    const px = parseFloat(cs.fontSize) || 0
    effSize = String(Math.round(isDocumentStyle ? (px * 72) / 96 : px))
  }
  // Reflect the effective font in the selects when it matches one of the
  // presets (e.g. Times New Roman inherited from .richtext-document), even
  // without an explicit textStyle mark — so the dropdown shows what's applied.
  const matchedFamily = STATIC_FONT_FAMILIES.find(f => f.label.toLowerCase() === effFamily.toLowerCase())
  const matchedSize = STATIC_FONT_SIZES.find(f => f.label === effSize)
  currentFontFamily.value = attrs.fontFamily || matchedFamily?.value || FONT_DEFAULT
  currentFontSize.value = attrs.fontSize || matchedSize?.value || FONT_DEFAULT
}

function applyFontFamily(val: string) {
  if (!editor.value) return
  const resolved = val === FONT_DEFAULT ? '' : val
  const cur = editor.value.getAttributes('textStyle') ?? {}
  const attrs = { ...cur, fontFamily: resolved || null }
  editor.value.chain().focus().setMark('textStyle', attrs).run()
  if (!resolved) editor.value.chain().focus().removeEmptyTextStyle().run()
  currentFontFamily.value = val
}

function applyFontSize(val: string) {
  if (!editor.value) return
  const resolved = val === FONT_DEFAULT ? '' : val
  const cur = editor.value.getAttributes('textStyle') ?? {}
  const attrs = { ...cur, fontSize: resolved || null }
  editor.value.chain().focus().setMark('textStyle', attrs).run()
  if (!resolved) editor.value.chain().focus().removeEmptyTextStyle().run()
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

// ── Alignment ─────────────────────────────────────────────────────────────────
const ALIGNMENTS = [
  { value: 'left', label: t('Align left'), icon: TextAlignStart },
  { value: 'center', label: t('Align center'), icon: TextAlignCenter },
  { value: 'right', label: t('Align right'), icon: TextAlignEnd },
  { value: 'justify', label: t('Justify'), icon: TextAlignJustify },
]

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
const isLinkOpen = ref(false)
const linkAnchorEl = ref<HTMLElement | null>(null)
const linkUrl  = ref('')

function openLinkPopover(event: Event) {
  if (!editor.value) return
  linkUrl.value = editor.value.getAttributes('link').href ?? ''
  linkAnchorEl.value = event.currentTarget as HTMLElement
  isLinkOpen.value = !isLinkOpen.value
}

function applyLink() {
  if (!editor.value) return
  const url = linkUrl.value.trim()
  url
    ? editor.value.chain().focus().extendMarkRange('link').setLink({ href: url }).run()
    : editor.value.chain().focus().extendMarkRange('link').unsetLink().run()
  isLinkOpen.value = false
}

function removeLink() {
  editor.value?.chain().focus().extendMarkRange('link').unsetLink().run()
  isLinkOpen.value = false
}

// ── Image ─────────────────────────────────────────────────────────────────────
const isImageOpen = ref(false)
const imageAnchorEl = ref<HTMLElement | null>(null)
const imageUrl       = ref('')
const imageUploading = ref(false)

function openImagePopover(event: Event) {
    imageAnchorEl.value = event.currentTarget as HTMLElement
    isImageOpen.value = !isImageOpen.value
}

function insertImageUrl() {
  const url = imageUrl.value.trim()
  if (url) editor.value?.chain().focus().setImage({ src: url }).run()
  imageUrl.value = ''
  isImageOpen.value = false
}

async function uploadImage(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  imageUploading.value = true
  try {
    const item = await filesApi.upload(file, uploadTarget())
    editor.value?.chain().focus().setImage({ src: item.url, alt: item.filename }).run()
    isImageOpen.value = false
  } catch (err) {
    toast.error(err instanceof Error ? err.message : String(err), t('Image upload failed'))
  } finally {
    imageUploading.value = false
    input.value = ''
  }
}

// ── YouTube video ─────────────────────────────────────────────────────────────
// The sanitizer (grunt/utils/sanitize.py) keeps the iframe but strips the
// extension's `data-youtube-video` wrapper marker, so saved and imported
// content is recognised by the embed src instead.
const YoutubeEmbed = Youtube.extend({
  parseHTML() {
    return [
      { tag: 'iframe[src*="youtube.com/embed/"]' },
      { tag: 'iframe[src*="youtube-nocookie.com/embed/"]' },
    ]
  },
})

const isVideoOpen = ref(false)
const videoAnchorEl = ref<HTMLElement | null>(null)
const videoUrl = ref('')

// A selected video is edited in place: the popover shows its link as a regular
// watch URL, and inserting over the node selection replaces it.
function openVideoPopover(event: Event) {
  const src: string = editor.value?.isActive('youtube') ? editor.value.getAttributes('youtube').src ?? '' : ''
  const id = src.match(/\/embed\/([\w-]+)/)?.[1]
  videoUrl.value = id ? `https://www.youtube.com/watch?v=${id}` : src
  videoAnchorEl.value = event.currentTarget as HTMLElement
  isVideoOpen.value = !isVideoOpen.value
}

function removeVideo() {
  editor.value?.chain().focus().deleteSelection().run()
  videoUrl.value = ''
  isVideoOpen.value = false
}

function insertVideo() {
  const src = videoUrl.value.trim()
  if (!src) return
  if (!editor.value?.chain().focus().setYoutubeVideo({ src }).run()) {
    toast.error(t('Paste a YouTube video link'), t('Invalid link'))
    return
  }
  videoUrl.value = ''
  isVideoOpen.value = false
}

// ── File list / gallery blocks ───────────────────────────────────────────────
const picker = ref<{ kind: FileBlockKind; resolve: (r: AttachmentResult[]) => void } | null>(null)

function pickFiles(kind: FileBlockKind): Promise<AttachmentResult[]> {
  picker.value?.resolve([])
  return new Promise((resolve) => { picker.value = { kind, resolve } })
}

function onPicked(results: AttachmentResult[]) {
  picker.value?.resolve(results)
  picker.value = null
}

async function insertFileBlock(kind: FileBlockKind) {
  const picked = await pickFiles(kind)
  if (!picked.length) return
  const content = kind === 'gallery'
    ? { type: 'gallery', attrs: { images: picked.map(toGalleryEntry) } }
    : { type: 'fileList', attrs: { files: picked.map(toFileEntry) } }
  editor.value?.chain().focus().insertContent(content).run()
}

// ── Word (.docx) import ──────────────────────────────────────────────────────
const docxInputEl = ref<HTMLInputElement | null>(null)
const docxImporting = ref(false)

function triggerDocxImport() {
  if (!docxImporting.value) docxInputEl.value?.click()
}

async function importDocx(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  docxImporting.value = true
  try {
    const arrayBuffer = await file.arrayBuffer()
    const { default: mammoth } = await import('mammoth')
    const { value: html, messages } = await mammoth.convertToHtml({ arrayBuffer })
    editor.value?.chain().focus().insertContent(html).run()
    const errors = messages.filter(m => m.type === 'error')
    if (errors.length) toast.warning(errors.map(m => m.message).join('; '), t('Imported with warnings'))
  } catch (err) {
    toast.error(err instanceof Error ? err.message : String(err), t('Could not import document'))
  } finally {
    docxImporting.value = false
    input.value = ''
  }
}

// ── Editor ────────────────────────────────────────────────────────────────────
let lastEmitted = ''

const editor = useEditor({
  content: String(props.modelValue ?? ''),
  editable: isEditable(),
  editorProps: {
    attributes: {
      role: 'textbox',
      'aria-multiline': 'true',
      'aria-label': props.field.label ?? t('Rich text'),
    },
  },
  extensions: [
    StarterKit.configure({
      link: false,
    }),
    RichTextStyle,
    IndentExt,
    TextAlign.configure({ types: ['paragraph', 'heading'] }),
    Link.configure({ openOnClick: false }),
    Image.configure({ inline: false }),
    TableKit,
    YoutubeEmbed.configure({
      nocookie: true,
      width: 640,
      height: 360,
      // YouTube refuses to play without a Referer (error 153); the element
      // attribute overrides a stricter page policy (e.g. a proxy's same-origin).
      HTMLAttributes: { referrerpolicy: 'strict-origin-when-cross-origin' },
    }),
    FileList.configure({ pick: pickFiles, t }),
    Gallery.configure({ pick: pickFiles, t }),
    Placeholder.configure({ placeholder: placeholderText.value }),
    CharacterCount.configure(maxLen.value ? { limit: maxLen.value } : {}),
  ],
  onUpdate: ({ editor: e }) => {
    lastEmitted = e.getHTML()
    emit('update:modelValue', lastEmitted)
    updateFormatState()
  },
  onSelectionUpdate: () => { updateBubble(); updateFormatState() },
  onBlur: () => { bubbleVisible.value = false },
})

watch(() => props.disabled,       () => editor.value?.setEditable(isEditable()))
watch(() => props.field.read_only, () => editor.value?.setEditable(isEditable()))
watch(() => props.modelValue, (v) => {
  const html = String(v ?? '')
  if (html === lastEmitted) return // our own echo — don't reset the caret
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
      role="toolbar"
      :aria-label="t('Formatting')"
      class="flex items-center gap-0.5 rounded-t-md border border-b-0 border-border bg-muted/50 p-1 flex-wrap text-foreground"
    >
      <!-- Font family -->
      <Select :model-value="currentFontFamily" @update:model-value="(v: unknown) => applyFontFamily(String(v))">
        <SelectTrigger class="h-7 w-36 text-xs" :aria-label="t('Font')">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem v-for="opt in FONT_FAMILIES" :key="opt.value" :value="opt.value">
            {{ opt.value === FONT_DEFAULT ? t('Default') : opt.label }}
          </SelectItem>
        </SelectContent>
      </Select>
      <!-- Font size -->
      <Select :model-value="currentFontSize" @update:model-value="(v: unknown) => applyFontSize(String(v))">
        <SelectTrigger class="h-7 w-[4.5rem] text-xs" :aria-label="t('Font size')">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem v-for="opt in FONT_SIZES" :key="opt.value" :value="opt.value">
            {{ opt.value === FONT_DEFAULT ? t('Auto') : opt.label }}
          </SelectItem>
        </SelectContent>
      </Select>

      <Separator orientation="vertical" class="!mx-1 !h-6 !my-0" />

      <Button size="sm" variant="ghost" :title="t('Bold')" :aria-label="t('Bold')" :aria-pressed="editor.isActive('bold')"
        :class="editor.isActive('bold') ? 'text-primary bg-accent' : 'text-muted-foreground'"
        :disabled="!editor.can().chain().focus().toggleBold().run()"
        @click="editor.chain().focus().toggleBold().run()">
        <Bold class="size-4" />
      </Button>
      <Button size="sm" variant="ghost" :title="t('Italic')" :aria-label="t('Italic')" :aria-pressed="editor.isActive('italic')"
        :class="editor.isActive('italic') ? 'text-primary bg-accent' : 'text-muted-foreground'"
        :disabled="!editor.can().chain().focus().toggleItalic().run()"
        @click="editor.chain().focus().toggleItalic().run()">
        <Italic class="size-4" />
      </Button>
      <Button size="sm" variant="ghost" :title="t('Strikethrough')" :aria-label="t('Strikethrough')" :aria-pressed="editor.isActive('strike')"
        :class="editor.isActive('strike') ? 'text-primary bg-accent' : 'text-muted-foreground'"
        :disabled="!editor.can().chain().focus().toggleStrike().run()"
        @click="editor.chain().focus().toggleStrike().run()">
        <Strikethrough class="size-4" />
      </Button>
      <Button size="sm" variant="ghost" :title="t('Inline code')" :aria-label="t('Inline code')" :aria-pressed="editor.isActive('code')"
        :class="editor.isActive('code') ? 'text-primary bg-accent' : 'text-muted-foreground'"
        :disabled="!editor.can().chain().focus().toggleCode().run()"
        @click="editor.chain().focus().toggleCode().run()">
        <Code class="size-4" />
      </Button>

      <Separator orientation="vertical" class="!mx-1 !h-6 !my-0" />

      <Button size="sm" variant="ghost" :title="t('Heading 2')" :aria-label="t('Heading 2')" :aria-pressed="editor.isActive('heading', { level: 2 })"
        :class="editor.isActive('heading', { level: 2 }) ? 'text-primary bg-accent' : 'text-muted-foreground'"
        @click="editor.chain().focus().toggleHeading({ level: 2 }).run()">
        <Heading2 class="size-4" />
      </Button>
      <Button size="sm" variant="ghost" :title="t('Heading 3')" :aria-label="t('Heading 3')" :aria-pressed="editor.isActive('heading', { level: 3 })"
        :class="editor.isActive('heading', { level: 3 }) ? 'text-primary bg-accent' : 'text-muted-foreground'"
        @click="editor.chain().focus().toggleHeading({ level: 3 }).run()">
        <Heading3 class="size-4" />
      </Button>

      <Separator orientation="vertical" class="!mx-1 !h-6 !my-0" />

      <Button size="sm" variant="ghost" :title="t('Bulleted list')" :aria-label="t('Bulleted list')" :aria-pressed="editor.isActive('bulletList')"
        :class="editor.isActive('bulletList') ? 'text-primary bg-accent' : 'text-muted-foreground'"
        @click="editor.chain().focus().toggleBulletList().run()">
        <List class="size-4" />
      </Button>
      <Button size="sm" variant="ghost" :title="t('Numbered list')" :aria-label="t('Numbered list')" :aria-pressed="editor.isActive('orderedList')"
        :class="editor.isActive('orderedList') ? 'text-primary bg-accent' : 'text-muted-foreground'"
        @click="editor.chain().focus().toggleOrderedList().run()">
        <ListOrdered class="size-4" />
      </Button>
      <Button size="sm" variant="ghost" :title="t('Quote')" :aria-label="t('Quote')" :aria-pressed="editor.isActive('blockquote')"
        :class="editor.isActive('blockquote') ? 'text-primary bg-accent' : 'text-muted-foreground'"
        @click="editor.chain().focus().toggleBlockquote().run()">
        <Quote class="size-4" />
      </Button>

      <!-- Alignment -->
      <Button v-for="a in ALIGNMENTS" :key="a.value" size="sm" variant="ghost" :title="a.label" :aria-label="a.label"
        :aria-pressed="editor.isActive({ textAlign: a.value })"
        :class="editor.isActive({ textAlign: a.value }) ? 'text-primary bg-accent' : 'text-muted-foreground'"
        @click="editor.chain().focus().toggleTextAlign(a.value).run()">
        <component :is="a.icon" class="size-4" />
      </Button>

      <!-- Indent / Outdent -->
      <Button size="sm" variant="ghost" :title="t('Increase indent')" :aria-label="t('Increase indent')" @click="doIndent">
        <IndentIncrease class="size-4" />
      </Button>
      <Button size="sm" variant="ghost" :title="t('Decrease indent')" :aria-label="t('Decrease indent')" @click="doOutdent">
        <IndentDecrease class="size-4" />
      </Button>

      <Button size="sm" variant="ghost" :title="t('Code block')" :aria-label="t('Code block')" :aria-pressed="editor.isActive('codeBlock')"
        :class="editor.isActive('codeBlock') ? 'text-primary bg-accent' : 'text-muted-foreground'"
        @click="editor.chain().focus().toggleCodeBlock().run()">
        <Code2 class="size-4" />
      </Button>
      <Button size="sm" variant="ghost" :title="t('Horizontal rule')" :aria-label="t('Horizontal rule')"
        @click="editor.chain().focus().setHorizontalRule().run()">
        <Minus class="size-4" />
      </Button>

      <Separator orientation="vertical" class="!mx-1 !h-6 !my-0" />

      <!-- Link -->
      <Button size="sm" variant="ghost" :title="t('Link')" :aria-label="t('Link')" :aria-pressed="editor.isActive('link')"
        :class="editor.isActive('link') ? 'text-primary bg-accent' : 'text-muted-foreground'" @click="openLinkPopover">
        <LinkIcon class="size-4" />
      </Button>
      <Popover v-model:open="isLinkOpen">
        <PopoverAnchor :reference="linkAnchorEl ?? undefined" />
        <PopoverContent class="w-auto p-0">
          <div class="w-72 p-1">
              <p class="font-medium text-muted-foreground mb-2">{{ t('Link') }}</p>
              <div class="flex gap-2">
                <Input v-model="linkUrl" placeholder="https://…" class="h-8 flex-1" :aria-label="t('Link URL')"
                  @keydown.enter.prevent="applyLink" />
                <Button size="sm" class="h-8 px-3" @click="applyLink">OK</Button>
                <Button v-if="editor.isActive('link')" variant="ghost" size="sm" class="h-8 px-2 text-destructive hover:text-destructive"
                  :aria-label="t('Remove link')" @click="removeLink">
                  <Link2Off class="size-4" />
                </Button>
              </div>
          </div>
        </PopoverContent>
      </Popover>

      <!-- Image -->
      <Button size="sm" variant="ghost" :title="t('Image')" :aria-label="t('Image')" @click="openImagePopover">
        <ImageIcon class="size-4" />
      </Button>
      <Popover v-model:open="isImageOpen">
        <PopoverAnchor :reference="imageAnchorEl ?? undefined" />
        <PopoverContent class="w-auto p-0">
          <div class="w-72 p-1">
              <p class="font-medium text-muted-foreground mb-2">{{ t('Image') }}</p>
              <div class="flex gap-2 mb-2">
                <Input v-model="imageUrl" placeholder="https://…" class="h-8 flex-1" :aria-label="t('Image URL')"
                  @keydown.enter.prevent="insertImageUrl" />
                <Button size="sm" class="h-8 px-3" @click="insertImageUrl">OK</Button>
              </div>
              <label class="flex items-center gap-2 cursor-pointer text-muted-foreground hover:text-foreground transition-colors p-2 hover:bg-muted rounded">
                <Upload class="size-3.5" />
                <span>{{ imageUploading ? t('Uploading…') : t('Upload file') }}</span>
                <input type="file" accept="image/*" class="hidden" :disabled="imageUploading" @change="uploadImage" />
              </label>
          </div>
        </PopoverContent>
      </Popover>

      <!-- YouTube video -->
      <Button size="sm" variant="ghost" :title="t('YouTube video')" :aria-label="t('YouTube video')"
        :aria-pressed="editor.isActive('youtube')"
        :class="editor.isActive('youtube') ? 'text-primary bg-accent' : 'text-muted-foreground'" @click="openVideoPopover">
        <Video class="size-4" />
      </Button>
      <Popover v-model:open="isVideoOpen">
        <PopoverAnchor :reference="videoAnchorEl ?? undefined" />
        <PopoverContent class="w-auto p-0">
          <div class="w-80 p-1">
              <p class="font-medium text-muted-foreground mb-2">{{ t('YouTube video') }}</p>
              <div class="flex gap-2">
                <Input v-model="videoUrl" placeholder="https://www.youtube.com/watch?v=…" class="h-8 flex-1"
                  :aria-label="t('Video URL')" @keydown.enter.prevent="insertVideo" />
                <Button size="sm" class="h-8 px-3" @click="insertVideo">OK</Button>
                <Button v-if="editor.isActive('youtube')" variant="ghost" size="sm" class="h-8 px-2 text-destructive hover:text-destructive"
                  :title="t('Remove video')" :aria-label="t('Remove video')" @click="removeVideo">
                  <Trash2 class="size-4" />
                </Button>
              </div>
          </div>
        </PopoverContent>
      </Popover>

      <!-- File list / gallery -->
      <Button size="sm" variant="ghost" :title="t('Files')" :aria-label="t('Files')" class="text-muted-foreground"
        @click="insertFileBlock('fileList')">
        <Paperclip class="size-4" />
      </Button>
      <Button size="sm" variant="ghost" :title="t('Gallery')" :aria-label="t('Gallery')" class="text-muted-foreground"
        @click="insertFileBlock('gallery')">
        <Images class="size-4" />
      </Button>

      <!-- Import from Word -->
      <Button size="sm" variant="ghost" :title="t('Import from Word (.docx)')" :aria-label="t('Import from Word (.docx)')" :disabled="docxImporting"
        class="text-muted-foreground" @click="triggerDocxImport">
        <Loader2 v-if="docxImporting" class="size-4 animate-spin" />
        <FileUp v-else class="size-4" />
      </Button>
      <input ref="docxInputEl" type="file" accept=".docx" class="hidden" @change="importDocx" />
      <AttachPicker
        :open="!!picker"
        :image-only="picker?.kind === 'gallery'"
        multiple
        :attached-to-doctype="uploadTarget().attachedToDoctype"
        :attached-to-id="uploadTarget().attachedToId"
        @update:open="(open: boolean) => { if (!open) onPicked([]) }"
        @select="(r: AttachmentResult) => onPicked([r])"
        @select-many="onPicked"
      />

      <Separator orientation="vertical" class="!mx-1 !h-6 !my-0" />

      <!-- Table -->
      <Button size="sm" variant="ghost" :title="t('Table')" :aria-label="t('Table')" :aria-pressed="editor.isActive('table')"
        :class="editor.isActive('table') ? 'text-primary bg-accent' : 'text-muted-foreground'"
        @click="editor.isActive('table')
          ? editor.chain().focus().deleteTable().run()
          : editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()">
        <TableIcon class="size-4" />
      </Button>

      <div class="flex-1" />

      <Button size="sm" variant="ghost" :title="t('Undo')" :aria-label="t('Undo')"
        :disabled="!editor.can().chain().focus().undo().run()"
        @click="editor.chain().focus().undo().run()">
        <Undo class="size-4" />
      </Button>
      <Button size="sm" variant="ghost" :title="t('Redo')" :aria-label="t('Redo')"
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
          class="absolute z-20 flex items-center gap-0.5 rounded-md border border-border bg-background/95 shadow-md p-1 text-foreground pointer-events-auto"
        >
          <Button size="sm" variant="ghost" :class="editor!.isActive('bold') ? 'text-primary bg-accent' : 'text-muted-foreground'"
            @click="editor!.chain().focus().toggleBold().run()">
            <Bold class="size-3.5" />
          </Button>
          <Button size="sm" variant="ghost" :class="editor!.isActive('italic') ? 'text-primary bg-accent' : 'text-muted-foreground'"
            @click="editor!.chain().focus().toggleItalic().run()">
            <Italic class="size-3.5" />
          </Button>
          <Button size="sm" variant="ghost" :class="editor!.isActive('strike') ? 'text-primary bg-accent' : 'text-muted-foreground'"
            @click="editor!.chain().focus().toggleStrike().run()">
            <Strikethrough class="size-3.5" />
          </Button>
          <Separator orientation="vertical" class="!mx-0.5 !h-5 !my-0" />
          <Button size="sm" variant="ghost" :class="editor!.isActive('link') ? 'text-primary bg-accent' : 'text-muted-foreground'" @click="openLinkPopover">
            <LinkIcon class="size-3.5" />
          </Button>
        </div>
      </Transition>

      <EditorContent :editor="editor" class="richtext-content p-3 text-foreground" :class="isDocumentStyle ? 'richtext-document' : ''" />
    </div>

    <!-- ── Footer (error is rendered by FieldRenderer) ────────────────── -->
    <div class="flex justify-end">
      <p v-if="editor" class="text-muted-foreground tabular-nums" aria-live="off">
        <template v-if="maxLen">{{ charCount() }} / {{ maxLen }}</template>
        <template v-else>{{ t('{words} w · {chars} ch', { words: wordCount(), chars: charCount() }) }}</template>
      </p>
    </div>

  </div>
</template>

<style>
.richtext-content .tiptap {
  outline: none;
  min-height: 96px;
  font-family: 'Geist Variable', 'Inter', ui-sans-serif, system-ui, sans-serif;
}
.richtext-content .tiptap > :first-child { margin-top: 0; }

/* Placeholder */
.richtext-content .tiptap p.is-editor-empty:first-child::before {
  content: attr(data-placeholder);
  color: var(--muted-foreground);
  pointer-events: none;
  float: left;
  height: 0;
}

.richtext-content .tiptap p { margin: 0.25rem 0; }

/* Document style: mirrors official-letter print formatting (first-line indent,
   justified text) so editing looks like the printed result. Opt-in via
   field.options === 'document'. */
.richtext-content.richtext-document .tiptap {
  font-family: 'Times New Roman', Times, serif;
  font-size: 14pt; /* matches the OutgoingLetter print format body */
}
.richtext-content.richtext-document .tiptap p {
  text-align: justify;
  text-indent: 1.25cm;
  margin: 0;
}
.richtext-content.richtext-document .tiptap p.is-editor-empty:first-child::before {
  text-indent: 0;
}

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
  background-color: var(--muted);
  border-radius: 0.3rem;
  font-size: 0.85em;
  padding: 0.2em 0.4em;
  font-family: ui-monospace, monospace;
}
.richtext-content .tiptap pre {
  background: var(--foreground);
  color: var(--background);
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
  border-left: 3px solid var(--border);
  margin: 0.75rem 0;
  padding-left: 1rem;
  color: var(--muted-foreground);
}
.richtext-content .tiptap hr {
  border: none;
  border-top: 1px solid var(--border);
  margin: 1.25rem 0;
}
.richtext-content .tiptap a {
  color: var(--primary);
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
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

/* YouTube embeds: full width, 16:9 */
.richtext-content .tiptap div[data-youtube-video] { margin: 0.5rem 0; }
.richtext-content .tiptap iframe {
  display: block;
  width: 100%;
  max-width: 640px;
  height: auto;
  aspect-ratio: 16 / 9;
  border: 0;
  border-radius: 0.375rem;
  pointer-events: none; /* let clicks select the node instead of playing */
}
.richtext-content .tiptap div[data-youtube-video].ProseMirror-selectednode iframe {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

/* File list / gallery blocks (fileBlocks.ts) */
.richtext-content .rt-file-block {
  margin: 0.75rem 0;
  padding: 0.5rem;
  border: 1px dashed var(--border);
  border-radius: 0.5rem;
}
.richtext-content .rt-file-block .file-list { display: flex; flex-direction: column; gap: 0.25rem; }
.richtext-content .rt-file-block .gallery {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 0.5rem;
}
.richtext-content .rt-file-block__item { position: relative; cursor: grab; }
.richtext-content .rt-file-block__item a { cursor: grab; }
.richtext-content .rt-file-block .file-list__meta { color: var(--muted-foreground); font-size: 0.85em; }
.richtext-content .rt-file-block .gallery__item { display: block; aspect-ratio: 4 / 3; overflow: hidden; border-radius: 0.375rem; }
.richtext-content .rt-file-block .gallery__item img { width: 100%; height: 100%; object-fit: cover; margin: 0; border-radius: 0; }
.richtext-content .rt-file-block__remove {
  position: absolute;
  top: 0.25rem;
  right: 0.25rem;
  width: 1.5rem;
  height: 1.5rem;
  line-height: 1;
  font-size: 1rem;
  border-radius: 9999px;
  background: var(--background);
  color: var(--muted-foreground);
  box-shadow: 0 1px 2px rgb(0 0 0 / 0.2);
  opacity: 0.85;
}
.richtext-content .rt-file-block__item:hover .rt-file-block__remove,
.richtext-content .rt-file-block__remove:focus-visible { opacity: 1; }
.richtext-content .rt-file-block__remove:hover { color: var(--destructive); }
.richtext-content .rt-file-block__actions { display: flex; gap: 1rem; margin-top: 0.5rem; }
.richtext-content .rt-file-block__add { color: var(--primary); }
.richtext-content .rt-file-block__delete { margin-left: auto; color: var(--muted-foreground); }
.richtext-content .rt-file-block__delete:hover { color: var(--destructive); }
.richtext-content .rt-file-block__add:hover,
.richtext-content .rt-file-block__delete:hover { text-decoration: underline; }

/* Tables */
.richtext-content .tiptap table {
  border-collapse: collapse;
  width: 100%;
  margin: 0.75rem 0;
  font-size: 0.875em;
}
.richtext-content .tiptap td,
.richtext-content .tiptap th {
  /* Dashed, not solid: this is an editing guide for cell boundaries, not
     ink — print formats don't style <table> at all, so a table imported
     from a borderless Word layout (e.g. a signature block) still prints
     without a border even though it shows a guide here while editing. */
  border: 1px dashed var(--border);
  padding: 0.4rem 0.6rem;
  vertical-align: top;
  min-width: 80px;
  position: relative;
}
.richtext-content .tiptap th {
  background-color: var(--muted);
  font-weight: 600;
}
.richtext-content .tiptap .selectedCell::after {
  content: '';
  position: absolute;
  inset: 0;
  background: var(--primary);
  opacity: 0.1;
  pointer-events: none;
}
.richtext-content .tiptap .column-resize-handle {
  position: absolute;
  right: -2px;
  top: 0; bottom: 0;
  width: 4px;
  background-color: var(--primary);
  cursor: col-resize;
  pointer-events: all;
}
.richtext-content .tiptap .tableWrapper { overflow-x: auto; }

/* Bubble menu transition */
.bubble-enter-active, .bubble-leave-active { transition: opacity 0.12s, transform 0.12s; }
.bubble-enter-from, .bubble-leave-to { opacity: 0; transform: translateY(4px); }
</style>
