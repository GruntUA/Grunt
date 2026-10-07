import type { Extensions } from '@tiptap/core'
import StarterKit from '@tiptap/starter-kit'
import { TextStyle, FontFamily, FontSize } from '@tiptap/extension-text-style'
import TextAlign from '@tiptap/extension-text-align'
import { TableKit } from '@tiptap/extension-table'
import FileHandler from '@tiptap/extension-file-handler'
import Highlight from '@tiptap/extension-highlight'
import Subscript from '@tiptap/extension-subscript'
import Superscript from '@tiptap/extension-superscript'
import Typography from '@tiptap/extension-typography'
import CharacterCount from '@tiptap/extension-character-count'
import Placeholder from '@tiptap/extension-placeholder'
import { Indent } from './indent'
import { RichImage } from './image'
import { DetailsKit } from './details'
import { SlashCommands, type SlashOptions } from './slash'
import { YoutubeEmbed } from './youtube'
import { RichTableCell, RichTableHeader } from './tableCells'
import { FileList, Gallery, type FileBlockOptions } from './fileBlocks'

export interface ExtensionOptions {
  placeholder: string
  maxLength?: number | null
  pickFiles: FileBlockOptions['pick']
  /** Files dropped or pasted into the text; `pos` is the drop point. */
  insertFiles: (files: File[], pos?: number) => void
  slash: SlashOptions
  t: FileBlockOptions['t']
}

/** Everything the RichText field can produce - keep in step with grunt/utils/sanitize.py. */
export function buildExtensions(o: ExtensionOptions): Extensions {
  return [
    StarterKit.configure({ link: { openOnClick: false } }),
    Highlight,
    Subscript,
    Superscript,
    // «Ukrainian» double quotes; the apostrophe stays a plain ' (м'ята), so
    // site search still matches what people type. Other rules (— … © →) as is.
    Typography.configure({ openDoubleQuote: '«', closeDoubleQuote: '»', openSingleQuote: false, closeSingleQuote: false }),
    TextStyle,
    FontFamily,
    FontSize,
    Indent,
    TextAlign.configure({ types: ['paragraph', 'heading'] }),
    RichImage,
    // Column widths are kept (from Word, or dragged by hand) so a table keeps
    // its layout on the public page instead of being re-flowed by the browser.
    TableKit.configure({ table: { resizable: true }, tableCell: false, tableHeader: false }),
    RichTableCell,
    RichTableHeader,
    YoutubeEmbed,
    ...DetailsKit,
    FileList.configure({ pick: o.pickFiles, t: o.t }),
    Gallery.configure({ pick: o.pickFiles, t: o.t }),
    FileHandler.configure({
      onDrop: (_, files, pos) => o.insertFiles(files, pos),
      // Copying from Word or a web page also puts a picture of the selection on
      // the clipboard; the HTML is what's wanted there, so files are taken
      // only from a plain file paste.
      onPaste: (_, files, html) => { if (!html) o.insertFiles(files) },
    }),
    SlashCommands.configure(o.slash),
    Placeholder.configure({ placeholder: o.placeholder }),
    CharacterCount.configure(o.maxLength ? { limit: o.maxLength } : {}),
  ]
}
