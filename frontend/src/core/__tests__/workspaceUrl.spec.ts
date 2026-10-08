import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAppStore } from '@/stores/app'
import { useDocTypeStore } from '@/stores/doctype'
import { appUrl, docUrl, workspaceFor } from '@/core/workspaceUrl'

describe('workspaceUrl', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    useAppStore().workspaces = [
      { name: 'grunt', items: [{ type: 'DocType', link_to: 'User' }] },
      {
        name: 'letter',
        items: [
          { type: 'DocType', link_to: 'IncomingLetter' },
          { type: 'Report', link_to: 'Monthly' },
          { type: 'Page', link_to: 'letter-home' },
          { type: 'DocType', link_to: 'LetterSettings', is_singleton: true },
        ],
      },
    ] as any
  })

  it('builds canonical /app paths', () => {
    expect(appUrl({ type: 'Workspace', name: 'letter' })).toBe('/app/letter')
    expect(appUrl({ type: 'Report', name: 'Monthly' })).toBe('/app/letter/report/Monthly')
    expect(appUrl({ type: 'Page', name: 'letter-home' })).toBe('/app/letter/page/letter-home')
    expect(docUrl('IncomingLetter', null, 'letter')).toBe('/app/letter/IncomingLetter')
    expect(docUrl('IncomingLetter', 'new', 'letter')).toBe('/app/letter/IncomingLetter/new')
  })

  it('returns URL links as is', () => {
    expect(appUrl({ type: 'URL', name: 'https://example.com/a?b=1' })).toBe('https://example.com/a?b=1')
  })

  it('encodes segments and appends the query', () => {
    expect(docUrl('Актив', 'a/b c', 'inventory')).toBe(
      `/app/inventory/${encodeURIComponent('Актив')}/a%2Fb%20c`,
    )
    expect(appUrl({ name: 'ToDo', workspace: 'grunt', query: { 'filter[status__eq]': 'Open', empty: '', none: null } }))
      .toBe('/app/grunt/ToDo?filter%5Bstatus__eq%5D=Open')
  })

  it('resolves the workspace by link type when none is given', () => {
    expect(workspaceFor('DocType', 'IncomingLetter')).toBe('letter')
    expect(docUrl('IncomingLetter', 'X-1')).toBe('/app/letter/IncomingLetter/X-1')
    expect(workspaceFor('DocType', 'Unknown')).toBe('grunt')
  })

  it('falls back to grunt without any workspaces', () => {
    useAppStore().workspaces = []
    expect(docUrl('ToDo', 't1')).toBe('/app/grunt/ToDo/t1')
  })

  it('collapses any singleton document id to the short URL', () => {
    expect(docUrl('LetterSettings', '0c7078584e')).toBe('/app/letter/LetterSettings')
    expect(docUrl('LetterSettings', 'new')).toBe('/app/letter/LetterSettings/new')
    useDocTypeStore().cache.set('Cfg', { name: 'Cfg', label: 'Cfg', module: 'x', is_singleton: true } as any)
    expect(docUrl('Cfg', 'Cfg', 'grunt')).toBe('/app/grunt/Cfg')
  })
})
