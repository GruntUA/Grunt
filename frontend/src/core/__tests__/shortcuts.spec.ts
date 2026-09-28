import { describe, expect, it } from 'vitest'

import { formatShortcut, matchesShortcut, shortcutKeys } from '@/core/shortcuts'

const ev = (init: KeyboardEventInit) => new KeyboardEvent('keydown', init)

describe('matchesShortcut', () => {
  it('Mod = Ctrl on Windows/Linux, ⌘ on macOS', () => {
    expect(matchesShortcut(ev({ key: 's', ctrlKey: true }), 'Mod+S', false)).toBe(true)
    expect(matchesShortcut(ev({ key: 's', metaKey: true }), 'Mod+S', false)).toBe(false)
    expect(matchesShortcut(ev({ key: 's', metaKey: true }), 'Mod+S', true)).toBe(true)
    expect(matchesShortcut(ev({ key: 's', ctrlKey: true }), 'Mod+S', true)).toBe(false)
    // `Ctrl` in a declaration is the primary modifier too.
    expect(matchesShortcut(ev({ key: 's', metaKey: true }), 'Ctrl+S', true)).toBe(true)
  })

  it('checks every modifier', () => {
    expect(matchesShortcut(ev({ key: 's' }), 'Mod+S', false)).toBe(false)
    expect(matchesShortcut(ev({ key: 'S', ctrlKey: true, shiftKey: true }), 'Mod+S', false)).toBe(false)
    expect(matchesShortcut(ev({ key: 'S', ctrlKey: true, shiftKey: true }), 'Mod+Shift+S', false)).toBe(true)
    expect(matchesShortcut(ev({ key: 's', ctrlKey: true, altKey: true }), 'Mod+S', false)).toBe(false)
  })

  it('uses the physical key on a non-Latin layout', () => {
    expect(matchesShortcut(ev({ key: 'і', code: 'KeyS', ctrlKey: true }), 'Mod+S', false)).toBe(true)
    expect(matchesShortcut(ev({ key: 'ї', code: 'BracketRight', metaKey: true }), 'Mod+]', true)).toBe(true)
    // ⌥N on macOS is a dead key («˜»); ⌥S types «ß».
    expect(matchesShortcut(ev({ key: 'Dead', code: 'KeyN', altKey: true }), 'Alt+N', true)).toBe(true)
    expect(matchesShortcut(ev({ key: 'ß', code: 'KeyS', altKey: true }), 'Alt+S', true)).toBe(true)
    expect(matchesShortcut(ev({ key: 'n', code: 'KeyN', altKey: true }), 'Alt+N', false)).toBe(true)
    // A Latin layout that moves keys (Dvorak) keeps matching by the character.
    expect(matchesShortcut(ev({ key: 'o', code: 'KeyS', ctrlKey: true }), 'Mod+S', false)).toBe(false)
  })

  it('matches named keys', () => {
    expect(matchesShortcut(ev({ key: 'Escape' }), 'Escape', false)).toBe(true)
    expect(matchesShortcut(ev({ key: 'Escape' }), 'Esc', false)).toBe(true)
    expect(matchesShortcut(ev({ key: 'Enter', ctrlKey: true }), 'Mod+Enter', false)).toBe(true)
  })
})

describe('formatting', () => {
  it('per platform', () => {
    expect(shortcutKeys('Mod+Shift+P', true)).toEqual(['⇧', '⌘', 'P'])
    expect(shortcutKeys('Mod+Shift+P', false)).toEqual(['Ctrl', 'Shift', 'P'])
    expect(formatShortcut('Mod+S', true)).toBe('⌘S')
    expect(formatShortcut('Mod+S', false)).toBe('Ctrl+S')
    expect(formatShortcut('Escape', false)).toBe('Esc')
    expect(formatShortcut('Alt+N', true)).toBe('⌥N')
    expect(formatShortcut('Alt+N', false)).toBe('Alt+N')
  })
})
