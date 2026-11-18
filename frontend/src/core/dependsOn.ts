/**
 * Evaluate a field/section `depends_on` expression against the current document.
 *
 * Accepts an optional `eval:` prefix, or a bare fieldname (`is_tree`), which
 * means "that field is truthy". Returns `true` when there is no expression,
 * and - deliberately - also when the expression throws, so a broken rule fails
 * open (the field stays visible) rather than hiding content.
 */
export function evalDependsOn(
  expr: string | null | undefined,
  doc: Record<string, unknown>,
): boolean {
  if (!expr) return true
  if (/^[A-Za-z_]\w*$/.test(expr) && expr !== 'true' && expr !== 'false') return !!doc?.[expr]
  return run(expr, doc, true)
}

/**
 * Evaluate a `mandatory_depends_on` / `read_only_depends_on` condition - the
 * same syntax as {@link evalDependsOn}, but it fails *closed*: no expression,
 * or one that throws, is `false` (the field stays optional / editable).
 * Evaluated in the form only; the server doesn't check these conditions.
 */
export function evalCondition(
  expr: string | null | undefined,
  doc: Record<string, unknown>,
): boolean {
  if (!expr) return false
  if (/^[A-Za-z_]\w*$/.test(expr) && expr !== 'true' && expr !== 'false') return !!doc?.[expr]
  return run(expr, doc, false)
}

function run(expr: string, doc: Record<string, unknown>, onError: boolean): boolean {
  const body = expr.replace(/^eval:\s*/, '')
  // `doc.__islocal` - not saved yet (no created_at; the name may already be typed in).
  const scope = { ...(doc ?? {}), __islocal: !doc?.created_at }
  try {
    // eslint-disable-next-line no-new-func
    return !!new Function('doc', `return !!(${body})`)(scope)
  } catch {
    return onError
  }
}
