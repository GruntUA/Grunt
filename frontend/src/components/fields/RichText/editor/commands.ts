/**
 * Every action of the RichText editor, described once.
 *
 * Toolbar buttons, menu items and bubble menus are all rendered from this
 * table (CommandButton / CommandMenuItem), so a command's label, icon,
 * shortcut hint, "is active" and "can run" checks live in one place.
 */
import type { ChainedCommands, Editor } from '@tiptap/core'
import type { Component } from 'vue'
import {
  Bold, Italic, Strikethrough, Code, Code2, Pilcrow, Heading2, Heading3, Quote,
  List, ListOrdered, IndentIncrease, IndentDecrease, Minus, Undo, Redo,
  TextAlignStart, TextAlignCenter, TextAlignEnd, TextAlignJustify,
  BetweenHorizontalStart, BetweenHorizontalEnd, BetweenVerticalStart, BetweenVerticalEnd,
  TableCellsMerge, TableCellsSplit, PanelTop, PanelLeft, Rows3, Columns3, Trash2,
  AlignVerticalJustifyStart, AlignVerticalJustifyCenter, AlignVerticalJustifyEnd, MoveRight, MoveDown, MoveUp,
  Underline, Highlighter, Subscript, Superscript, ListCollapse,
  Link2Off, PanelLeftDashed, PanelRightDashed, SquareCenterlineDashedHorizontal,
} from '@lucide/vue'
import type { ImageAlign } from '../extensions/image'
import { N_ } from '@/plugins/i18n'

export interface EditorCommand {
  /** English i18n key. */
  label: string
  icon: Component
  /** Shortcut hint for tooltips and menus. */
  keys?: string
  isActive?: (editor: Editor) => boolean
  run: (chain: ChainedCommands, editor: Editor) => ChainedCommands
  destructive?: boolean
}

const active = (name: string, attrs?: Record<string, unknown>) => (e: Editor) => e.isActive(name, attrs)
const cellAttr = (name: string, value: unknown) => (e: Editor) =>
  e.getAttributes(e.isActive('tableHeader') ? 'tableHeader' : 'tableCell')[name] === value

export const COMMANDS = {
  // Block style
  paragraph: { label: N_('Paragraph'), icon: Pilcrow, keys: 'Ctrl+Alt+0', run: c => c.clearNodes() },
  heading2: { label: N_('Heading 2'), icon: Heading2, keys: 'Ctrl+Alt+2', isActive: active('heading', { level: 2 }), run: c => c.setHeading({ level: 2 }) },
  heading3: { label: N_('Heading 3'), icon: Heading3, keys: 'Ctrl+Alt+3', isActive: active('heading', { level: 3 }), run: c => c.setHeading({ level: 3 }) },
  blockquote: { label: N_('Quote'), icon: Quote, keys: 'Ctrl+Shift+B', isActive: active('blockquote'), run: c => c.toggleBlockquote() },
  codeBlock: { label: N_('Code block'), icon: Code2, keys: 'Ctrl+Alt+C', isActive: active('codeBlock'), run: c => c.toggleCodeBlock() },

  // Marks
  bold: { label: N_('Bold'), icon: Bold, keys: 'Ctrl+B', isActive: active('bold'), run: c => c.toggleBold() },
  italic: { label: N_('Italic'), icon: Italic, keys: 'Ctrl+I', isActive: active('italic'), run: c => c.toggleItalic() },
  underline: { label: N_('Underline'), icon: Underline, keys: 'Ctrl+U', isActive: active('underline'), run: c => c.toggleUnderline() },
  highlight: { label: N_('Highlight'), icon: Highlighter, keys: 'Ctrl+Shift+H', isActive: active('highlight'), run: c => c.toggleHighlight() },
  subscript: { label: N_('Subscript'), icon: Subscript, keys: 'Ctrl+,', isActive: active('subscript'), run: c => c.toggleSubscript() },
  superscript: { label: N_('Superscript'), icon: Superscript, keys: 'Ctrl+.', isActive: active('superscript'), run: c => c.toggleSuperscript() },
  strike: { label: N_('Strikethrough'), icon: Strikethrough, keys: 'Ctrl+Shift+S', isActive: active('strike'), run: c => c.toggleStrike() },
  code: { label: N_('Inline code'), icon: Code, keys: 'Ctrl+E', isActive: active('code'), run: c => c.toggleCode() },

  // Lists, alignment, indent
  bulletList: { label: N_('Bulleted list'), icon: List, keys: 'Ctrl+Shift+8', isActive: active('bulletList'), run: c => c.toggleBulletList() },
  orderedList: { label: N_('Numbered list'), icon: ListOrdered, keys: 'Ctrl+Shift+7', isActive: active('orderedList'), run: c => c.toggleOrderedList() },
  alignLeft: { label: N_('Align left'), icon: TextAlignStart, keys: 'Ctrl+Shift+L', isActive: e => e.isActive({ textAlign: 'left' }), run: c => c.setTextAlign('left') },
  alignCenter: { label: N_('Align center'), icon: TextAlignCenter, keys: 'Ctrl+Shift+E', isActive: e => e.isActive({ textAlign: 'center' }), run: c => c.setTextAlign('center') },
  alignRight: { label: N_('Align right'), icon: TextAlignEnd, keys: 'Ctrl+Shift+R', isActive: e => e.isActive({ textAlign: 'right' }), run: c => c.setTextAlign('right') },
  alignJustify: { label: N_('Justify'), icon: TextAlignJustify, keys: 'Ctrl+Shift+J', isActive: e => e.isActive({ textAlign: 'justify' }), run: c => c.setTextAlign('justify') },
  indent: { label: N_('Increase indent'), icon: IndentIncrease, keys: 'Tab', run: c => c.indent() },
  outdent: { label: N_('Decrease indent'), icon: IndentDecrease, keys: 'Shift+Tab', run: c => c.outdent() },
  horizontalRule: { label: N_('Horizontal rule'), icon: Minus, run: c => c.setHorizontalRule() },
  details: { label: N_('Collapsible block'), icon: ListCollapse, isActive: active('details'), run: (c, e) => (e.isActive('details') ? c.unsetDetails() : c.setDetails()) },

  // History
  undo: { label: N_('Undo'), icon: Undo, keys: 'Ctrl+Z', run: c => c.undo() },
  redo: { label: N_('Redo'), icon: Redo, keys: 'Ctrl+Shift+Z', run: c => c.redo() },

  // Table
  addRowBefore: { label: N_('Insert row above'), icon: BetweenHorizontalStart, run: c => c.addRowBefore() },
  addRowAfter: { label: N_('Insert row below'), icon: BetweenHorizontalEnd, run: c => c.addRowAfter() },
  addColumnBefore: { label: N_('Insert column left'), icon: BetweenVerticalStart, run: c => c.addColumnBefore() },
  addColumnAfter: { label: N_('Insert column right'), icon: BetweenVerticalEnd, run: c => c.addColumnAfter() },
  deleteRow: { label: N_('Delete row'), icon: Rows3, destructive: true, run: c => c.deleteRow() },
  deleteColumn: { label: N_('Delete column'), icon: Columns3, destructive: true, run: c => c.deleteColumn() },
  deleteTable: { label: N_('Delete table'), icon: Trash2, destructive: true, run: c => c.deleteTable() },
  mergeCells: { label: N_('Merge cells'), icon: TableCellsMerge, run: c => c.mergeCells() },
  splitCell: { label: N_('Split cell'), icon: TableCellsSplit, run: c => c.splitCell() },
  toggleHeaderRow: { label: N_('Header row'), icon: PanelTop, isActive: e => isHeaderRow(e), run: c => c.toggleHeaderRow() },
  toggleHeaderColumn: { label: N_('Header column'), icon: PanelLeft, isActive: e => isHeaderColumn(e), run: c => c.toggleHeaderColumn() },
  cellAlignTop: { label: N_('Align top'), icon: AlignVerticalJustifyStart, isActive: cellAttr('verticalAlign', null), run: c => c.setCellAttribute('verticalAlign', null) },
  cellAlignMiddle: { label: N_('Align middle'), icon: AlignVerticalJustifyCenter, isActive: cellAttr('verticalAlign', 'middle'), run: c => c.setCellAttribute('verticalAlign', 'middle') },
  cellAlignBottom: { label: N_('Align bottom'), icon: AlignVerticalJustifyEnd, isActive: cellAttr('verticalAlign', 'bottom'), run: c => c.setCellAttribute('verticalAlign', 'bottom') },
  textHorizontal: { label: N_('Horizontal text'), icon: MoveRight, isActive: cellAttr('textDirection', null), run: c => c.setCellAttribute('textDirection', null) },
  textTopToBottom: { label: N_('Vertical text, top to bottom'), icon: MoveDown, isActive: cellAttr('textDirection', 'tb'), run: c => c.setCellAttribute('textDirection', 'tb') },
  textBottomToTop: { label: N_('Vertical text, bottom to top'), icon: MoveUp, isActive: cellAttr('textDirection', 'bt'), run: c => c.setCellAttribute('textDirection', 'bt') },

  // Link (cursor inside one)
  unsetLink: { label: N_('Remove link'), icon: Link2Off, run: c => c.extendMarkRange('link').unsetLink() },

  // Image (selected); alignment toggles back to "in the text flow"
  imageAlignLeft: { label: N_('Image left, text wraps'), icon: PanelLeftDashed, isActive: active('image', { align: 'left' }), run: (c, e) => alignImage(c, e, 'left') },
  imageAlignCenter: { label: N_('Image centered'), icon: SquareCenterlineDashedHorizontal, isActive: active('image', { align: 'center' }), run: (c, e) => alignImage(c, e, 'center') },
  imageAlignRight: { label: N_('Image right, text wraps'), icon: PanelRightDashed, isActive: active('image', { align: 'right' }), run: (c, e) => alignImage(c, e, 'right') },
  deleteSelection: { label: N_('Delete'), icon: Trash2, destructive: true, run: c => c.deleteSelection() },
} satisfies Record<string, EditorCommand>

function alignImage(chain: ChainedCommands, editor: Editor, align: ImageAlign) {
  return chain.updateAttributes('image', { align: editor.isActive('image', { align }) ? null : align })
}

export type CommandId = keyof typeof COMMANDS

export const command = (id: CommandId): EditorCommand => COMMANDS[id]

export const runCommand = (editor: Editor, id: CommandId) => command(id).run(editor.chain().focus(), editor).run()

export const canRunCommand = (editor: Editor, id: CommandId) => command(id).run(editor.can().chain(), editor).run()

export const isCommandActive = (editor: Editor, id: CommandId) => !!command(id).isActive?.(editor)

// The first row / column of the current table is all header cells.
function tableAt(editor: Editor) {
  const { $from } = editor.state.selection
  for (let d = $from.depth; d > 0; d--) if ($from.node(d).type.name === 'table') return $from.node(d)
  return null
}

function isHeaderRow(editor: Editor): boolean {
  const row = tableAt(editor)?.firstChild
  return !!row && row.childCount > 0 && row.content.content.every(cell => cell.type.name === 'tableHeader')
}

function isHeaderColumn(editor: Editor): boolean {
  const table = tableAt(editor)
  return !!table && table.content.content.every(row => row.firstChild?.type.name === 'tableHeader')
}

// Groups the toolbar and menus show as one control.
export const BLOCK_STYLES: CommandId[] = ['paragraph', 'heading2', 'heading3', 'blockquote', 'codeBlock']
export const ALIGNMENTS: CommandId[] = ['alignLeft', 'alignCenter', 'alignRight', 'alignJustify']

/** The active entry of a group; the first one is the fallback. */
export const activeIn = (editor: Editor, group: CommandId[]): CommandId =>
  group.slice(1).find(id => isCommandActive(editor, id)) ?? group[0]!
