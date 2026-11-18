import client from './client'
import type { ActiveFilter } from '@/types'

export type FilterSharing = 'Nobody' | 'Roles' | 'Everyone'

/** A saved set of list filters (grunt/api/v1/saved_filters.py). */
export interface SavedFilter {
  name: string
  title: string
  filters: ActiveFilter[]
  shared_with: FilterSharing
  roles: string[]
  /** The current user's own - only they change or delete it. */
  mine: boolean
}

const M = '/api/v1/method/grunt.api.v1.saved_filters'

export const savedFiltersApi = {
  /** The user's own filters on `doctype` and those shared with them. */
  list: async (doctype: string): Promise<SavedFilter[]> =>
    (await client.get(`${M}.list_saved_filters`, { params: { doctype } })).data.data ?? [],

  /** Create, or replace the user's filter of the same title. */
  save: async (
    doctype: string,
    title: string,
    filters: ActiveFilter[],
    sharedWith: FilterSharing = 'Nobody',
    roles: string[] = [],
  ): Promise<SavedFilter> =>
    (await client.post(`${M}.save_saved_filter`, { doctype, title, filters, shared_with: sharedWith, roles }))
      .data.data,

  remove: async (name: string): Promise<void> => {
    await client.post(`${M}.delete_saved_filter`, { name })
  },
}
