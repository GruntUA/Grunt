/** Field types the inline grid can edit directly; everything else opens the row dialog. */
export const INLINE_TYPES = new Set([
  'Text',
  'Int',
  'Float',
  'Check',
  'Select',
  'Date',
  'Datetime',
  'Time',
  'Link',
])

/**
 * "Grid cell" look for a shadcn Input inside a table cell: full width, flush,
 * transparent with a faint underline so an editable cell is discoverable at
 * rest; the full border appears on hover, the ring on focus. Keeps Input's
 * built-in aria-invalid styling for inline validation.
 */
export const CELL_INPUT_CLASS =
  'w-full h-8 rounded-none border-transparent border-b-border/30 bg-transparent px-3 text-xs shadow-none hover:border-input focus-visible:ring-0 focus-visible:border-ring'
