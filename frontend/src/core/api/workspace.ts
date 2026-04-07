import client from './client'
import type { DashboardWidget } from '@/types'

export interface WorkspaceLink {
  section: string
  type: 'DocType' | 'Report' | 'Dashboard' | 'URL' | 'Divider'
  label: string
  icon: string
  link_to: string
  show_count: boolean
  count_filters?: string
  show_new_btn: boolean
  roles: string
  sequence: number
  is_singleton?: boolean
}

export interface WorkspaceLinkItem {
  label: string
  icon?: string
  type: 'DocType' | 'Report' | 'Dashboard' | 'URL'
  link_to: string
  description?: string
}

export interface Workspace {
  name: string
  label: string
  app: string
  icon: string
  color: string
  description: string
  sequence: number
  is_hidden: boolean
  roles: string
  items: WorkspaceLink[]
  widgets: DashboardWidget[]
}

export interface SearchResult {
  doctype: string
  id: string
  name: string
  display_title: string
}

export const workspaceApi = {
  list: async (): Promise<Workspace[]> => {
    const r = await client.get('/api/v1/workspaces/')
    return r.data.data
  },

  get: async (name: string): Promise<Workspace> => {
    const r = await client.get(`/api/v1/workspaces/${name}`)
    return r.data.data
  },

  create: async (data: Partial<Workspace>): Promise<Workspace> => {
    const r = await client.post('/api/v1/workspaces/', data)
    return r.data.data
  },

  update: async (name: string, data: Partial<Workspace>): Promise<Workspace> => {
    const r = await client.put(`/api/v1/workspaces/${name}`, data)
    return r.data.data
  },

  delete: async (name: string): Promise<void> => {
    await client.delete(`/api/v1/workspaces/${name}`)
  },

  getCounts: async (name: string): Promise<Record<string, number>> => {
    const r = await client.get(`/api/v1/workspaces/${name}/counts`)
    return r.data.data
  },

  search: async (q: string, limit = 10): Promise<SearchResult[]> => {
    const r = await client.get('/api/v1/search', { params: { q, limit } })
    return r.data.data
  },

  getWidgetData: async (
    name: string,
    opts?: { dateFrom?: string; dateTo?: string },
  ): Promise<Record<string, unknown>> => {
    const r = await client.get(`/api/v1/workspaces/${name}/widget-data`, {
      params: { date_from: opts?.dateFrom, date_to: opts?.dateTo },
    })
    return r.data.data
  },
}
