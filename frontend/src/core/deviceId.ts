/**
 * Stable random id of this browser, kept in the `grunt_device` cookie.
 *
 * The server reads it at sign-in: every sign-in from the same browser reuses
 * one UserSession row instead of adding a new one. Rewritten on every boot,
 * since browsers cap cookie lifetime at about 400 days.
 */
const COOKIE = 'grunt_device'
const MAX_AGE = 400 * 24 * 60 * 60

function readCookie(): string | null {
    const match = document.cookie.match(new RegExp(`(?:^|; )${COOKIE}=([0-9a-f]{32})`))
    return match ? match[1] : null
}

function randomId(): string {
    const bytes = crypto.getRandomValues(new Uint8Array(16))
    return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
}

export function ensureDeviceId(): void {
    const id = readCookie() ?? randomId()
    const secure = location.protocol === 'https:' ? '; secure' : ''
    document.cookie = `${COOKIE}=${id}; path=/; max-age=${MAX_AGE}; samesite=lax${secure}`
}
