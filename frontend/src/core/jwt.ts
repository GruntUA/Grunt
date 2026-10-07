/** True when a JWT's `exp` has passed (with a 5 s skew window). */
export function isJwtExpired(jwt: string): boolean {
  try {
    const payloadPart = jwt.split('.')[1]
    if (!payloadPart) return false
    const base64 = payloadPart.replace(/-/g, '+').replace(/_/g, '/')
    const json = atob(base64)
    const payload = JSON.parse(json)
    if (typeof payload?.exp !== 'number') return false
    // Consider a small skew window to avoid racing token expiry.
    return payload.exp * 1000 <= Date.now() + 5_000
  } catch {
    // Non-JWT token format: treat as non-expiring on client side.
    return false
  }
}
