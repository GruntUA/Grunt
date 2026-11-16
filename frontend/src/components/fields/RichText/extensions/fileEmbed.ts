/**
 * File embed for the RichText editor - a PDF, Word, Excel or PowerPoint file
 * shown right in the text, with a download link under it.
 *
 * Stored as plain HTML that needs no script on the page:
 *
 *   <figure class="file-embed">
 *     <iframe src="/api/v1/files/<id>.pdf" title="Name.pdf" loading="lazy" …></iframe>
 *     <figcaption><a href="…get_content?file_id=<id>">Name.pdf</a>
 *       <span class="file-embed__meta">PDF · 240 KB</span></figcaption>
 *   </figure>
 *
 * A PDF is shown by the browser from the site itself; Word / Excel /
 * PowerPoint go through Office for the web (view.officeapps.live.com), which
 * fetches the file anonymously by its address on this site - so it shows
 * once the file is public (the document is published, see
 * grunt.storage.references). Both read the file by ``/api/v1/files/<id>.<ext>``:
 * the viewer picks the format by the extension at the end of the URL.
 *
 * The figcaption link is what ties the file to the document (claim / publish
 * on save) and what readers get where an <iframe> doesn't render (feeds, mail).
 */
import { Node } from '@tiptap/core'
import type { Node as PmNode } from '@tiptap/pm/model'
import type { NodeView, EditorView } from '@tiptap/pm/view'
import type { FileBlockOptions, FileEntry } from './fileBlocks'

export type FileEmbedOptions = Pick<FileBlockOptions, 't'>

export const OFFICE_VIEWER = 'https://view.officeapps.live.com/op/embed.aspx?src='
const OFFICE_EXTENSIONS = new Set(['doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx'])
const FILE_ID = /get_content\?file_id=([A-Za-z0-9_-]+)/

export function fileExtension(name: string): string {
  return /\.([A-Za-z0-9]+)$/.exec(name)?.[1].toLowerCase() ?? ''
}

/** Whether a file of this name can be shown in the text. */
export function canEmbed(name: string): boolean {
  const ext = fileExtension(name)
  return ext === 'pdf' || OFFICE_EXTENSIONS.has(ext)
}

const isPdf = (name: string) => fileExtension(name) === 'pdf'

/**
 * The stored <iframe> src for a file: its public address on this site, for
 * Word / Excel / PowerPoint wrapped in the Office viewer (which needs the
 * absolute URL). Null for a file that can't be embedded.
 */
export function embedSrc(url: string, name: string, origin = window.location.origin): string | null {
  const id = FILE_ID.exec(url)?.[1]
  if (!id || !canEmbed(name)) return null
  const path = `/api/v1/files/${id}.${fileExtension(name)}`
  return isPdf(name) ? path : OFFICE_VIEWER + encodeURIComponent(origin + path)
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
 * Editing view. The file usually isn't public yet while it's being written,
 * so a PDF is previewed by its signed URL and an Office file - which the
 * Office viewer can't fetch until it's published - by a note instead.
 */
class FileEmbedView implements NodeView {
  dom: HTMLElement
  private node: PmNode

  constructor(
    node: PmNode,
    private view: EditorView,
    private getPos: () => number | undefined,
    private options: FileEmbedOptions,
  ) {
    this.node = node
    this.dom = el('div', { class: 'rt-file-block rt-file-embed', contenteditable: 'false' })
    this.render()
  }

  private render() {
    const { t } = this.options
    const { url, name, meta } = this.node.attrs as FileEntry
    const preview = isPdf(name)
      ? el('iframe', { src: `${url}&inline=1`, title: name, loading: 'lazy' })
      : el('div', { class: 'rt-file-embed__note' },
          t('Word, Excel and PowerPoint files are shown on the published page'))
    const caption = el('div', { class: 'rt-file-embed__caption' })
    const link = el('a', { href: url, target: '_blank', rel: 'noopener' }, name)
    caption.append(link)
    if (meta) caption.append(' ', el('span', { class: 'file-embed__meta' }, meta))
    this.dom.replaceChildren(preview, caption)
    if (!this.view.editable) return
    // While editing, a click on the name must not download the file.
    link.addEventListener('click', (e) => e.preventDefault())
    const actions = el('div', { class: 'rt-file-block__actions' })
    const drop = el('button', { type: 'button', class: 'rt-file-block__delete' }, t('Delete file preview'))
    drop.addEventListener('click', () => {
      const pos = this.getPos()
      if (pos !== undefined) this.view.dispatch(this.view.state.tr.delete(pos, pos + this.node.nodeSize))
    })
    actions.append(drop)
    this.dom.append(actions)
  }

  update(node: PmNode) {
    if (node.type !== this.node.type) return false
    // Re-rendering reloads the <iframe> - only when the file itself changed.
    const changed = node.attrs.url !== this.node.attrs.url || node.attrs.meta !== this.node.attrs.meta
    this.node = node
    if (changed) this.render()
    return true
  }

  stopEvent() {
    return true
  }

  ignoreMutation() {
    return true
  }
}

export const FileEmbed = Node.create<FileEmbedOptions>({
  name: 'fileEmbed',
  group: 'block',
  atom: true,
  draggable: true,

  addOptions() {
    return { t: (key: string) => key }
  },

  addAttributes() {
    const caption = (dom: HTMLElement) => dom.querySelector('figcaption a[href]')
    return {
      url: { default: '', parseHTML: (dom: HTMLElement) => caption(dom)?.getAttribute('href') ?? '', renderHTML: () => ({}) },
      name: { default: '', parseHTML: (dom: HTMLElement) => caption(dom)?.textContent?.trim() ?? '', renderHTML: () => ({}) },
      meta: {
        default: '',
        parseHTML: (dom: HTMLElement) => dom.querySelector('.file-embed__meta')?.textContent?.trim() ?? '',
        renderHTML: () => ({}),
      },
    }
  },

  // Ahead of the image's <figure>, should one ever claim figures.
  parseHTML() {
    return [{ tag: 'figure.file-embed', priority: 100 }]
  },

  renderHTML({ node }) {
    const { url, name, meta } = node.attrs as FileEntry
    const src = embedSrc(url, name)
    return ['figure', { class: 'file-embed' },
      ...(src
        ? [['iframe', {
            src,
            title: name,
            loading: 'lazy',
            allowfullscreen: 'true',
            // Pages without the site's stylesheet still get a usable frame.
            width: '100%',
            height: '720',
          }]]
        : []),
      ['figcaption', {},
        ['a', { href: url }, name],
        ...(meta ? [' ', ['span', { class: 'file-embed__meta' }, meta]] : []),
      ],
    ] as any
  },

  addNodeView() {
    return ({ node, view, getPos }) => new FileEmbedView(node, view, getPos, this.options)
  },
})
