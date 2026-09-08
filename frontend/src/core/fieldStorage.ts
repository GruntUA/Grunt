/**
 * Storage-class hints for the DocType «Конструктор».
 *
 * Mirrors the backend `sa_factory` column mapping (grunt/metadata/field types)
 * closely enough to tell the user, when they change a field's `fieldtype` in the
 * builder, whether the underlying database column will be retyped — or added /
 * dropped — during the next `doctype sync`.
 *
 * This is a UI heads-up only. Nothing here mutates the field: existing values
 * are kept as-is and the authoritative migration still runs on sync.
 */

export type StorageClass =
  | 'text' // String / Text column
  | 'int' // Integer column
  | 'float' // Float / Numeric column
  | 'bool' // Boolean column
  | 'date'
  | 'datetime'
  | 'time'
  | 'json' // JSON blob column
  | 'none' // no column of its own (layout, Table, MultiLink, Button, …)

const STORAGE_CLASS: Record<string, StorageClass> = {
  // ── String / Text columns ──
  Data: 'text',
  Text: 'text',
  LongText: 'text',
  RichText: 'text',
  HTMLEditor: 'text',
  Code: 'text',
  Signature: 'text',
  Select: 'text',
  Link: 'text',
  DynamicLink: 'text',
  Attach: 'text',
  Image: 'text',
  Icon: 'text',
  Color: 'text',
  BarCode: 'text',
  Password: 'text',
  // ── Numeric ──
  Int: 'int',
  Check: 'bool',
  Float: 'float',
  Duration: 'float',
  Percent: 'float',
  Rating: 'float',
  // ── Temporal ──
  Date: 'date',
  Datetime: 'datetime',
  Time: 'time',
  // ── JSON blobs ──
  JSON: 'json',
  Geolocation: 'json',
  ColumnMapping: 'json',
  EmbeddedForm: 'json',
  MultiSelect: 'json',
  // ── No column of their own ──
  Button: 'none',
  Default: 'none',
  Section: 'none',
  Column: 'none',
  Tab: 'none',
  Table: 'none',
  MultiLink: 'none',
}

/** Storage class for a field type. Unknown / plugin types are assumed text. */
export function storageClassOf(fieldtype: string): StorageClass {
  return STORAGE_CLASS[fieldtype] ?? 'text'
}

export type TypeChangeSeverity = 'info' | 'danger'

export interface TypeChangeNote {
  severity: TypeChangeSeverity
  message: string
}

/**
 * Retypes the database can widen losslessly — every existing value survives the
 * implicit cast. Keyed `"<from>-><to>"` on storage class.
 */
const SAFE_WIDENINGS = new Set<string>([
  'int->float',
  'int->text',
  'bool->int',
  'bool->float',
  'bool->text',
  'float->text',
  'date->datetime',
  'date->text',
  'datetime->text',
  'time->text',
])

/**
 * Describe what a `from` → `to` fieldtype change does to already-stored data.
 * Returns `null` when the column is untouched (same storage class, e.g.
 * `Data` ↔ `Text` ↔ `Select`, or `from === to`).
 */
export function describeTypeChange(from: string, to: string): TypeChangeNote | null {
  if (from === to) return null

  const a = storageClassOf(from)
  const b = storageClassOf(to)
  if (a === b) return null

  if (a === 'none' || b === 'none') {
    return {
      severity: 'danger',
      message:
        'Новий тип зберігає значення інакше (окрема колонка або дочірня таблиця). '
        + 'Наявні дані цього поля не переносяться автоматично — вивантажте їх до міграції.',
    }
  }

  if (SAFE_WIDENINGS.has(`${a}->${b}`)) {
    return {
      severity: 'info',
      message: 'Тип колонки в БД зміниться під час міграції. Наявні значення сумісні й зберігаються.',
    }
  }

  return {
    severity: 'danger',
    message:
      'Тип колонки в БД зміниться під час міграції. Значення, які не вдасться привести до нового типу, '
      + 'можуть не зберегтися — перевірте наявні дані.',
  }
}
