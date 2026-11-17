/**
 * A permission rule's row condition (`DocPermission.match`) - the grammar the
 * server accepts (grunt.metadata.permission.MATCH_RE):
 *
 *   <field> | <link_field>.<target_field>   ==|!=   user | 'value'
 */

export interface RowCondition {
  /** A field of the document. */
  field: string
  /** A field of the document `field` links to - one Link hop. */
  sub: string
  op: '==' | '!='
  /** `user` - the current user; otherwise a text value. */
  kind: 'user' | 'value'
  value: string
}

const MATCH = /^([A-Za-z_]\w*)(?:\.([A-Za-z_]\w*))?\s*(==|!=)\s*(.+)$/

/** The condition as parts, or null when the text is outside the grammar. */
export function parseCondition(text: string | null | undefined): RowCondition | null {
  const m = MATCH.exec((text ?? '').trim())
  if (!m) return null
  const raw = m[4].trim()
  const base = { field: m[1], sub: m[2] ?? '', op: m[3] as '==' | '!=' }
  if (raw === 'user') return { ...base, kind: 'user', value: '' }
  const quoted = /^'([^']*)'$/.exec(raw) ?? /^"([^"]*)"$/.exec(raw)
  if (!quoted) return null
  return { ...base, kind: 'value', value: quoted[1] }
}

/**
 * The condition as text; '' when no field is chosen yet; null when the value
 * holds both quote kinds - the grammar can't say that, and dropping a
 * character would make the rule match other rows.
 */
export function formatCondition(c: RowCondition): string | null {
  if (!c.field) return ''
  const left = c.sub ? `${c.field}.${c.sub}` : c.field
  if (c.kind === 'user') return `${left} ${c.op} user`
  if (c.value.includes("'") && c.value.includes('"')) return null
  // A value with a single quote is written in double quotes.
  const quoted = c.value.includes("'") ? `"${c.value}"` : `'${c.value}'`
  return `${left} ${c.op} ${quoted}`
}
