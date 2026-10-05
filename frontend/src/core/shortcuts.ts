/**
 * Keyboard shortcuts: one notation for declaring, matching and showing them.
 *
 * A shortcut is `Mod+S`, `Mod+Shift+P`, `Escape`, `Alt+Enter`… - `Mod` (also
 * spelled `Ctrl` / `Cmd` / `Meta`) is the platform's primary modifier: ⌘ on
 * macOS / iOS, Ctrl elsewhere.
 *
 * Matching falls back to the physical key (`event.code`) when the layout is not
 * Latin, so Ctrl+S works on a Ukrainian layout, where `event.key` is «і»,
 * and for ⌥-combinations on macOS, where Option changes the character.
 */

type NavigatorWithUAData = Navigator & { userAgentData?: { platform?: string } }

function detectMac(): boolean {
  if (typeof navigator === 'undefined') return false
  const nav = navigator as NavigatorWithUAData
  const platform = nav.userAgentData?.platform || nav.platform || nav.userAgent
  return /mac|iphone|ipad|ipod/i.test(platform)
}

export const IS_MAC = detectMac()

interface ParsedShortcut {
  mod: boolean
  shift: boolean
  alt: boolean
  key: string
}

const MOD_ALIASES = new Set(['mod', 'ctrl', 'control', 'cmd', 'command', 'meta'])
const KEY_ALIASES: Record<string, string> = { esc: 'escape', return: 'enter', del: 'delete', space: ' ' }

function parse(shortcut: string): ParsedShortcut {
  const parts = shortcut.toLowerCase().split('+').map((p) => p.trim())
  // `Mod++` - the last part is the key itself.
  const raw = parts.pop() || '+'
  return {
    mod: parts.some((p) => MOD_ALIASES.has(p)),
    shift: parts.includes('shift'),
    alt: parts.includes('alt') || parts.includes('option'),
    key: KEY_ALIASES[raw] ?? raw,
  }
}

const CODE_KEYS: Record<string, string> = {
  BracketLeft: '[', BracketRight: ']', Comma: ',', Period: '.', Slash: '/', Backslash: '\\',
  Semicolon: ';', Quote: "'", Backquote: '`', Minus: '-', Equal: '=',
}

/** The Latin key under the finger: `KeyS` -> `s`, `Digit1` -> `1`, `BracketRight` -> `]`. */
function physicalKey(code: string): string | undefined {
  if (/^Key[A-Z]$/.test(code)) return code.slice(3).toLowerCase()
  if (/^Digit\d$/.test(code)) return code.slice(5)
  return CODE_KEYS[code]
}

/** Does a keydown event match `shortcut`? `mac` picks the primary modifier (⌘ vs Ctrl). */
export function matchesShortcut(event: KeyboardEvent, shortcut: string, mac = IS_MAC): boolean {
  const want = parse(shortcut)
  const primary = mac ? event.metaKey : event.ctrlKey
  const other = mac ? event.ctrlKey : event.metaKey
  if (want.mod !== primary || other || want.alt !== event.altKey) return false
  // Shift is part of a symbol (`?` = Shift+/), so only check it for letters/named keys.
  if (want.shift !== event.shiftKey && !(want.key.length === 1 && !/[a-z0-9]/.test(want.key))) return false

  const key = (event.key ?? '').toLowerCase()
  if (key === want.key) return true
  // Non-Latin layout (Cyrillic, Greek…), or Option on macOS that turns the key
  // into another symbol (⌥N -> «˜», a dead key): compare the physical key instead.
  const nonLatin = key.length === 1 && key.charCodeAt(0) > 127
  const macOption = mac && event.altKey
  return (nonLatin || macOption || key === 'dead') && physicalKey(event.code) === want.key
}

const MAC_SYMBOLS: Record<string, string> = { mod: '⌘', shift: '⇧', alt: '⌥' }
const PC_NAMES: Record<string, string> = { mod: 'Ctrl', shift: 'Shift', alt: 'Alt' }
const KEY_LABELS: Record<string, string> = {
  escape: 'Esc', enter: '↵', backspace: '⌫', delete: 'Del', tab: 'Tab', ' ': 'Space',
  arrowup: '↑', arrowdown: '↓', arrowleft: '←', arrowright: '→',
}

/** Key caps to render, in order: `['⌘', 'S']` on macOS, `['Ctrl', 'S']` elsewhere. */
export function shortcutKeys(shortcut: string, mac = IS_MAC): string[] {
  const p = parse(shortcut)
  const names = mac ? MAC_SYMBOLS : PC_NAMES
  // macOS order is ⌥⇧⌘, Windows/Linux - Ctrl+Shift+Alt.
  const mods = mac
    ? [p.alt && names.alt, p.shift && names.shift, p.mod && names.mod]
    : [p.mod && names.mod, p.shift && names.shift, p.alt && names.alt]
  const key = KEY_LABELS[p.key] ?? (p.key.length === 1 ? p.key.toUpperCase() : p.key[0].toUpperCase() + p.key.slice(1))
  return [...mods.filter((m): m is string => !!m), key]
}

/** Plain-text form for titles / aria / menus: `⌘S` on macOS, `Ctrl+S` elsewhere. */
export function formatShortcut(shortcut: string, mac = IS_MAC): string {
  return shortcutKeys(shortcut, mac).join(mac ? '' : '+')
}
