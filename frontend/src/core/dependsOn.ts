/**
 * Evaluate a field/section `depends_on` expression against the current document.
 *
 * Accepts an optional `eval:` prefix. Returns `true` when there
 * is no expression, and - deliberately - also when the expression throws, so a
 * broken rule fails open (the field stays visible) rather than hiding content.
 */
export function evalDependsOn(
  expr: string | null | undefined,
  doc: Record<string, unknown>,
): boolean {
  if (!expr) return true
  const body = expr.replace(/^eval:\s*/, '')
  try {
    // eslint-disable-next-line no-new-func
    return !!new Function('doc', `return !!(${body})`)(doc ?? {})
  } catch {
    return true
  }
}
