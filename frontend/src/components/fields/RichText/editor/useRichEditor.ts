import { inject, onBeforeUnmount, provide, reactive, ref, watch, type InjectionKey, type ShallowRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { useEditor, type Editor } from '@tiptap/vue-3'
import { Image as ImageIcon, Images, Paperclip, Table as TableIcon } from '@lucide/vue'
import type { DocField } from '@/types'
import { filesApi, type FileItem } from '@/core/api/files'
import type { AttachmentResult } from '@/core/attachmentChannels/types'
import type { DocContext } from '@/components/fields/Attach/useAttachmentField'
import { useToast } from '@/core/composables/useToast'
import { buildExtensions } from '../extensions'
import { toFileEntry, toGalleryEntry, type FileBlockKind } from '../extensions/fileBlocks'
import { docxToHtml } from '../extensions/docx'
import type { SlashItem, SlashMenuState } from '../extensions/slash'
import { command, type CommandId } from './commands'

export interface RichEditorProps {
  field: DocField
  modelValue: unknown
  disabled?: boolean
  maxLength?: number
  placeholder?: string
}

/**
 * The tiptap editor of a RichText field plus the actions that need more than
 * an editor command: uploads, the file picker, Word import.
 */
export function useRichEditor(props: RichEditorProps, emit: (e: 'update:modelValue', v: unknown) => void) {
  const { t } = useI18n()
  const toast = useToast()

  const editable = () => !props.disabled && !props.field.read_only
  // FieldRenderer passes only field / modelValue / disabled / error, so limit
  // and placeholder come from the field (explicit props override them).
  const maxLength = () => props.maxLength ?? props.field.max_length

  // Uploads made here are pending attachments of this DocType; the document
  // claims the ones its text refers to when saved (grunt.storage.references).
  const docContext = inject<DocContext | null>('docContext', null)
  const uploadTarget = () => ({
    attachedToDoctype: docContext?.doctype,
    attachedToId: docContext?.getId() ?? undefined,
  })

  // File picker (AttachPicker) for the file list / gallery blocks
  const picker = ref<{ kind: FileBlockKind; resolve: (r: AttachmentResult[]) => void } | null>(null)

  function pickFiles(kind: FileBlockKind): Promise<AttachmentResult[]> {
    picker.value?.resolve([])
    return new Promise((resolve) => { picker.value = { kind, resolve } })
  }

  function onPicked(results: AttachmentResult[]) {
    picker.value?.resolve(results)
    picker.value = null
  }

  // "/" menu: registry commands plus the inserts that need a file
  const slash = reactive<SlashMenuState>({ items: [], index: 0, rect: null, choose: null })

  const SLASH_COMMANDS: [CommandId, string][] = [
    ['paragraph', 'text p'], ['heading2', 'h2 title'], ['heading3', 'h3 subtitle'],
    ['bulletList', 'ul bullet'], ['orderedList', 'ol number'], ['blockquote', 'quote'],
    ['details', 'details faq toggle'], ['codeBlock', 'code pre'], ['horizontalRule', 'hr divider line'],
  ]

  const slashItems = (): SlashItem[] => [
    ...SLASH_COMMANDS.map(([id, keywords]): SlashItem => ({
      id, keywords, label: t(command(id).label), icon: command(id).icon,
      run: (e, range) => command(id).run(e.chain().focus().deleteRange(range), e).run(),
    })),
    { id: 'table', keywords: 'grid', label: t('Table'), icon: TableIcon,
      run: (e, range) => e.chain().focus().deleteRange(range).insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run() },
    { id: 'image', keywords: 'picture photo img', label: t('Image'), icon: ImageIcon,
      run: async (e, range) => {
        e.chain().focus().deleteRange(range).run()
        const file = await chooseFile('image/*')
        if (file) uploadImage(file)
      } },
    { id: 'files', keywords: 'attachment pdf', label: t('Files'), icon: Paperclip,
      run: (e, range) => { e.chain().focus().deleteRange(range).run(); insertFileBlock('fileList') } },
    { id: 'gallery', keywords: 'images photos', label: t('Gallery'), icon: Images,
      run: (e, range) => { e.chain().focus().deleteRange(range).run(); insertFileBlock('gallery') } },
  ]

  let lastEmitted = ''

  const editor = useEditor({
    content: String(props.modelValue ?? ''),
    editable: editable(),
    editorProps: {
      attributes: {
        role: 'textbox',
        'aria-multiline': 'true',
        'aria-label': props.field.label ?? t('Rich text'),
      },
    },
    extensions: buildExtensions({
      placeholder: props.placeholder ?? props.field.placeholder ?? t('Type / for commands'),
      maxLength: maxLength(),
      pickFiles,
      insertFiles: (files, pos) => insertFiles(files, pos),
      slash: { items: slashItems, state: slash },
      t,
    }),
    onUpdate: ({ editor: e }) => {
      lastEmitted = e.getHTML()
      emit('update:modelValue', lastEmitted)
    },
  })

  // No update event: setEditable would re-emit the editor's own serialization,
  // which differs from the sanitized HTML the server returns (form goes dirty
  // right after saving, when the form is re-enabled).
  watch(() => [props.disabled, props.field.read_only], () => editor.value?.setEditable(editable(), false))
  watch(() => props.modelValue, (v) => {
    const html = String(v ?? '')
    if (html === lastEmitted) return // our own echo - don't reset the caret
    if (editor.value && editor.value.getHTML() !== html)
      editor.value.commands.setContent(html, { emitUpdate: false })
  })

  onBeforeUnmount(() => editor.value?.destroy())

  // Busy flags for the toolbar spinner
  const uploading = ref(false)

  async function busy<T>(work: () => Promise<T>, errorTitle: string): Promise<T | undefined> {
    uploading.value = true
    try {
      return await work()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err), errorTitle)
    } finally {
      uploading.value = false
    }
  }

  async function uploadImage(file: File) {
    const item = await busy(() => filesApi.upload(file, uploadTarget()), t('Image upload failed'))
    if (item) editor.value?.chain().focus().setImage({ src: item.url, alt: item.filename }).run()
    return !!item
  }

  /** Upload dropped / pasted files: images go in as images, the rest as one file list. */
  async function insertFiles(files: File[], pos?: number) {
    const uploaded = await busy(() => Promise.all(files.map(f => filesApi.upload(f, uploadTarget()))), t('Upload failed'))
    if (!uploaded) return
    const isImage = (f: FileItem) => f.content_type.startsWith('image/')
    const others = uploaded.filter(f => !isImage(f))
    const content = [
      ...uploaded.filter(isImage).map(f => ({ type: 'image', attrs: { src: f.url, alt: f.filename } })),
      ...(others.length ? [{ type: 'fileList', attrs: { files: others.map(fileEntry) } }] : []),
    ]
    const chain = editor.value?.chain().focus()
    ;(pos === undefined ? chain?.insertContent(content) : chain?.insertContentAt(pos, content))?.run()
  }

  async function insertFileBlock(kind: FileBlockKind) {
    const picked = await pickFiles(kind)
    if (!picked.length) return
    const content = kind === 'gallery'
      ? { type: 'gallery', attrs: { images: picked.map(toGalleryEntry) } }
      : { type: 'fileList', attrs: { files: picked.map(toFileEntry) } }
    editor.value?.chain().focus().insertContent(content).run()
  }

  async function importDocx(file: File) {
    const result = await busy(() => docxToHtml(file), t('Could not import document'))
    if (!result) return
    editor.value?.chain().focus().insertContent(result.html).run()
    if (result.warnings.length) toast.warning(result.warnings.join('; '), t('Imported with warnings'))
  }

  /** Native file dialog, for actions started from the keyboard ("/" menu). */
  function chooseFile(accept: string): Promise<File | null> {
    return new Promise((resolve) => {
      const input = Object.assign(document.createElement('input'), { type: 'file', accept })
      input.addEventListener('change', () => resolve(input.files?.[0] ?? null), { once: true })
      input.addEventListener('cancel', () => resolve(null), { once: true })
      input.click()
    })
  }

  /** For a menu's close-auto-focus: hand focus back to the text, not the menu button. */
  function refocus(e: Event) {
    e.preventDefault()
    editor.value?.commands.focus()
  }

  return {
    editor,
    refocus,
    slash,
    editable,
    maxLength,
    uploadTarget,
    picker,
    onPicked,
    uploading,
    uploadImage,
    insertFileBlock,
    importDocx,
  }
}

const fileEntry = (f: FileItem) => toFileEntry({ url: f.url, filename: f.filename, contentType: f.content_type, fileItem: f })

export type RichEditor = ReturnType<typeof useRichEditor>

const richEditorKey: InjectionKey<RichEditor> = Symbol('richEditor')

export const provideRichEditor = (rich: RichEditor) => provide(richEditorKey, rich)

export function useRichEditorContext(): RichEditor {
  const rich = inject(richEditorKey)
  if (!rich) throw new Error('RichText editor context is missing')
  return rich
}

/** The editor instance, for components that only run commands. */
export const useEditorInstance = (): ShallowRef<Editor | undefined> => useRichEditorContext().editor
