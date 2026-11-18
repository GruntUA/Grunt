/**
 * Rounding to a field's precision - the same rules as grunt/utils/numbers.py
 * (FRAPPE_GAP_PLAN #5), so the form shows what the server will store.
 *
 * Works on the number's shortest decimal text (exponent shift, `1.005e2`), not
 * on `n * 100`: binary floats make `1.005 * 100` 100.49999…, so `Math.round`
 * would give 1.00 where the server's Decimal gives 1.01.
 *
 * The method is the site's `rounding_method` (site config):
 * - `Half up` (commercial, default) - a 5 goes away from zero: 0.125 -> 0.13;
 * - `Half even` (banker's) - a 5 goes to the even digit: 0.125 -> 0.12.
 */
import { siteConfigState } from '@/core/composables/useSiteConfig'

export type RoundingMethod = 'Half up' | 'Half even'

/** `n * 10^p` through the decimal text, so the shift itself adds no float error. */
function shift(n: number, p: number): number {
  const [mantissa, exp] = String(n).split('e')
  return Number(`${mantissa}e${Number(exp ?? 0) + p}`)
}

export function roundNumber(n: number, precision: number, method: RoundingMethod = 'Half up'): number {
  if (!Number.isFinite(n)) return n
  const sign = n < 0 ? -1 : 1
  const scaled = shift(Math.abs(n), precision)
  let whole = Math.floor(scaled)
  const rest = scaled - whole
  if (rest > 0.5 || (rest === 0.5 && (method === 'Half up' || whole % 2 === 1))) whole += 1
  const out = shift(whole, -precision) * sign
  return out === 0 ? 0 : out // no -0
}

/** The site's rounding method (`Half up` until the site config loads). */
export function siteRounding(): RoundingMethod {
  return siteConfigState().roundingMethod === 'Half even' ? 'Half even' : 'Half up'
}

/** `n` rounded to `precision` by the site's method; as is without a precision. */
export function roundToPrecision(n: number, precision: number | null | undefined): number {
  return precision == null ? n : roundNumber(n, precision, siteRounding())
}
