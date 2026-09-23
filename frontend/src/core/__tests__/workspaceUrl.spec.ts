import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAppStore } from '@/stores/app'
import { docUrl, workspaceForDoctype, workspaceUrl } from '@/core/workspaceUrl'

describe('workspaceUrl', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    useAppStore().workspaces = [
      { name: 'grunt', items: [{ type: 'DocType', link_to: 'User' }] },
      { name: 'letter', items: [{ type: 'DocType', link_to: 'IncomingLetter' }] },
    ] as any
  })

  it('builds canonical /app paths', () => {
    expect(workspaceUrl('letter', 'report', 'Monthly')).toBe('/app/letter/report/Monthly')
    expect(docUrl('IncomingLetter', null, 'letter')).toBe('/app/letter/IncomingLetter')
    expect(docUrl('IncomingLetter', 'new', 'letter')).toBe('/app/letter/IncomingLetter/new')
  })

  it('encodes doctype and id segments', () => {
    expect(docUrl('Актив', 'a/b c', 'inventory')).toBe(
      `/app/inventory/${encodeURIComponent('Актив')}/a%2Fb%20c`,
    )
  })

  it('resolves the workspace by doctype when none is given', () => {
    expect(workspaceForDoctype('IncomingLetter')).toBe('letter')
    expect(docUrl('IncomingLetter', 'X-1')).toBe('/app/letter/IncomingLetter/X-1')
    expect(workspaceForDoctype('Unknown')).toBe('grunt')
  })

  it('falls back to grunt without any workspaces', () => {
    useAppStore().workspaces = []
    expect(docUrl('ToDo', 't1')).toBe('/app/grunt/ToDo/t1')
  })
})
