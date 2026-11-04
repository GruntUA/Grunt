import { afterEach, describe, expect, it, vi } from 'vitest'

import { openUrl } from '@/core/composables/useDocActions'

describe('openUrl', () => {
  afterEach(() => vi.restoreAllMocks())

  it('opens http(s) and relative URLs in a new tab', () => {
    const open = vi.spyOn(window, 'open').mockReturnValue({} as Window)
    openUrl('https://example.com/a.xlsx')
    openUrl('/files/b.csv')
    expect(open.mock.calls.map((c) => c[0])).toEqual([
      'https://example.com/a.xlsx',
      `${window.location.origin}/files/b.csv`,
    ])
  })

  it('ignores other schemes', () => {
    const open = vi.spyOn(window, 'open')
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    openUrl('javascript:alert(1)')
    expect(open).not.toHaveBeenCalled()
  })
})
