/**
 * File blocks for the RichText editor - a list of downloadable files and an
 * image gallery, each placed wherever the author wants it in the text.
 *
 * Both are stored as plain semantic HTML that renders without any script or
 * server-side expansion (web pages, e-mail, print formats):
 *
 *   <ul class="file-list"><li><a href="…get_content?file_id=…">Name.pdf</a>
 *     <span class="file-list__meta">PDF · 240 KB</span></li></ul>
 *   <div class="gallery"><a class="gallery__item" href="…"><img src="…" alt="…"></a></div>
 *
 * The gallery markup is the one the mlt_portal archive import already emits,
 * so imported and hand-made galleries parse into the same node. Files the
 * author uploads here are claimed by the document on save
 * (grunt.storage.references).
 */
import { Node } from '@tiptap/core'
import type { Node as PmNode } from '@tiptap/pm/model'
import type { NodeView, EditorView } from '@tiptap/pm/view'
import type { AttachmentResult } from '@/components/fields/Attach/attachment'
import { fileTypeLabel, formatFileSize } from '@/core/fileUtils'

export interface FileEntry {
  url: string
  name: string
  meta: string
}

export interface GalleryEntry {
  url: string
  src: string
  name: string
}

export type FileBlockKind = 'fileList' | 'gallery'

export interface FileBlockOptions {
  /** Open the file picker; resolves with the chosen files (empty on cancel). */
  pick: ((kind: FileBlockKind) => Promise<AttachmentResult[]>) | null
  t: (key: string) => string
}

export function toFileEntry(r: AttachmentResult): FileEntry {
  const size = r.fileItem?.size_bytes
  const parts = [fileTypeLabel(r.filename, r.contentType)]
  if (size) parts.push(formatFileSize(size))
  return { url: r.url, name: r.filename, meta: parts.join(' · ') }
}

export function toGalleryEntry(r: AttachmentResult): GalleryEntry {
  return { url: r.url, src: r.fileItem?.thumbnail_url || r.url, name: r.filename }
}

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  attrs: Record<string, string> = {},
  text?: string,
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag)
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v)
  if (text !== undefined) node.textContent = text
  return node
}

/**
 * Editing view shared by both blocks: the stored markup plus a remove button
 * per item, drag-to-reorder, and an "add" button that appends via the picker.
 */
class FileBlockView<T> implements NodeView {
  dom: HTMLElement
  private node: PmNode
  private dragFrom = -1

  constructor(
    node: PmNode,
    private view: EditorView,
    private getPos: () => number | undefined,
    private kind: FileBlockKind,
    private options: FileBlockOptions,
    private attr: 'files' | 'images',
    private renderItem: (item: T) => HTMLElement,
    private fromResult: (r: AttachmentResult) => T,
  ) {
    this.node = node
    this.dom = el('div', { class: `rt-file-block rt-file-block--${kind}`, contenteditable: 'false' })
    this.render()
  }

  private get items(): T[] {
    return (this.node.attrs[this.attr] as T[]) ?? []
  }

  private commit(items: T[]) {
    const pos = this.getPos()
    if (pos === undefined) return
    const tr = items.length
      ? this.view.state.tr.setNodeMarkup(pos, undefined, { ...this.node.attrs, [this.attr]: items })
      : this.view.state.tr.delete(pos, pos + this.node.nodeSize)
    this.view.dispatch(tr)
  }

  private render() {
    const { t } = this.options
    const editable = this.view.editable
    const list = el('div', { class: this.kind === 'gallery' ? 'gallery' : 'file-list' })
    this.items.forEach((item, i) => {
      const cell = el('div', { class: 'rt-file-block__item' })
      cell.append(this.renderItem(item))
      if (editable) {
        // Tiles and file names are links in the stored markup; while editing a
        // click must not open (i.e. download) the file.
        cell.addEventListener('click', (e) => {
          if ((e.target as HTMLElement).closest('a')) e.preventDefault()
        })
        cell.draggable = true
        cell.addEventListener('dragstart', (e) => {
          this.dragFrom = i
          e.dataTransfer?.setData('text/plain', '')
        })
        cell.addEventListener('dragover', (e) => e.preventDefault())
        cell.addEventListener('drop', (e) => {
          e.preventDefault()
          if (this.dragFrom < 0 || this.dragFrom === i) return
          const next = [...this.items]
          const [moved] = next.splice(this.dragFrom, 1)
          next.splice(i, 0, moved)
          this.dragFrom = -1
          this.commit(next)
        })
        const remove = el('button', {
          type: 'button',
          class: 'rt-file-block__remove',
          title: t('Remove'),
          'aria-label': t('Remove'),
        }, '×')
        remove.addEventListener('click', () => this.commit(this.items.filter((_, j) => j !== i)))
        cell.append(remove)
      }
      list.append(cell)
    })
    this.dom.replaceChildren(list)
    if (!editable) return
    const actions = el('div', { class: 'rt-file-block__actions' })
    if (this.options.pick) {
      const add = el('button', { type: 'button', class: 'rt-file-block__add' },
        this.kind === 'gallery' ? t('Add images') : t('Add files'))
      add.addEventListener('click', async () => {
        const picked = await this.options.pick!(this.kind)
        if (picked.length) this.commit([...this.items, ...picked.map(this.fromResult)])
      })
      actions.append(add)
    }
    const drop = el('button', { type: 'button', class: 'rt-file-block__delete' },
      this.kind === 'gallery' ? t('Delete gallery') : t('Delete file list'))
    drop.addEventListener('click', () => this.commit([]))
    actions.append(drop)
    this.dom.append(actions)
  }

  update(node: PmNode) {
    if (node.type !== this.node.type) return false
    this.node = node
    this.render()
    return true
  }

  // Clicks, drags and buttons inside the block are ours, not ProseMirror's.
  stopEvent() {
    return true
  }

  ignoreMutation() {
    return true
  }
}

function fileLink(item: FileEntry): HTMLElement {
  const li = el('span')
  li.append(el('a', { href: item.url, target: '_blank', rel: 'noopener' }, item.name))
  if (item.meta) li.append(' ', el('span', { class: 'file-list__meta' }, item.meta))
  return li
}

function galleryTile(item: GalleryEntry): HTMLElement {
  const a = el('a', { class: 'gallery__item', href: item.url, target: '_blank', rel: 'noopener' })
  a.append(el('img', { src: item.src, alt: item.name, loading: 'lazy' }))
  return a
}

export const FileList = Node.create<FileBlockOptions>({
  name: 'fileList',
  group: 'block',
  atom: true,

  addOptions() {
    return { pick: null, t: (key: string) => key }
  },

  addAttributes() {
    return {
      files: {
        default: [],
        parseHTML: (dom: HTMLElement): FileEntry[] =>
          Array.from(dom.querySelectorAll(':scope > li')).flatMap((li) => {
            const a = li.querySelector('a[href]')
            if (!a) return []
            return [{
              url: a.getAttribute('href') ?? '',
              name: a.textContent?.trim() ?? '',
              meta: li.querySelector('.file-list__meta')?.textContent?.trim() ?? '',
            }]
          }),
        renderHTML: () => ({}),
      },
    }
  },

  // Ahead of bulletList, which would otherwise take every <ul>.
  parseHTML() {
    return [{ tag: 'ul.file-list', priority: 100 }]
  },

  renderHTML({ node }) {
    const files = node.attrs.files as FileEntry[]
    return ['ul', { class: 'file-list' }, ...files.map((f) => [
      'li',
      ['a', { href: f.url }, f.name],
      ...(f.meta ? [' ', ['span', { class: 'file-list__meta' }, f.meta]] : []),
    ])] as any
  },

  addNodeView() {
    return ({ node, view, getPos }) =>
      new FileBlockView<FileEntry>(node, view, getPos, 'fileList', this.options, 'files', fileLink, toFileEntry)
  },
})

export const Gallery = Node.create<FileBlockOptions>({
  name: 'gallery',
  group: 'block',
  atom: true,

  addOptions() {
    return { pick: null, t: (key: string) => key }
  },

  addAttributes() {
    return {
      images: {
        default: [],
        parseHTML: (dom: HTMLElement): GalleryEntry[] =>
          Array.from(dom.querySelectorAll('a.gallery__item')).flatMap((a) => {
            const img = a.querySelector('img')
            if (!img) return []
            const src = img.getAttribute('src') ?? ''
            return [{ url: a.getAttribute('href') || src, src, name: img.getAttribute('alt') ?? '' }]
          }),
        renderHTML: () => ({}),
      },
    }
  },

  parseHTML() {
    return [{ tag: 'div.gallery', priority: 100 }]
  },

  renderHTML({ node }) {
    const images = node.attrs.images as GalleryEntry[]
    return ['div', { class: 'gallery' }, ...images.map((i) => [
      'a',
      { class: 'gallery__item', href: i.url },
      ['img', { src: i.src, alt: i.name, loading: 'lazy' }],
    ])] as any
  },

  addNodeView() {
    return ({ node, view, getPos }) =>
      new FileBlockView<GalleryEntry>(node, view, getPos, 'gallery', this.options, 'images', galleryTile, toGalleryEntry)
  },
})
