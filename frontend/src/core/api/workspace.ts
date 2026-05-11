import client from './client'

export interface WorkspaceLink {
  section: string
  type: 'DocType' | 'Report' | 'Page' | 'URL' | 'Divider'
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
  type: 'DocType' | 'Report' | 'Page' | 'URL'
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
  home_page: string | null
  items: WorkspaceLink[]
}

export interface SearchResult {
  doctype: string
  id: string
  name: string
  display_title: string
}

export const workspaceApi = {
  list: async (): Promise<Workspace[]> => {
    const r = await client.get('/api/v1/method/grunt.api.v1.workspace.list_workspaces')
    return r.data.data
  },

  get: async (name: string): Promise<Workspace> => {
    const r = await client.get('/api/v1/method/grunt.api.v1.workspace.get_workspace', { params: { name } })
    return r.data.data
  },

  create: async (data: Partial<Workspace>): Promise<Workspace> => {
    const r = await client.post('/api/v1/method/grunt.api.v1.workspace.save_workspace', data)
    return r.data.data
  },

  update: async (name: string, data: Partial<Workspace>): Promise<Workspace> => {
    const payload = { ...data, name }
    const r = await client.post('/api/v1/method/grunt.api.v1.workspace.save_workspace', payload)
    return r.data.data
  },

  delete: async (name: string): Promise<void> => {
    await client.post('/api/v1/method/grunt.api.v1.workspace.delete_workspace', { name })
  },

  getCounts: async (name: string): Promise<Record<string, number>> => {
    const r = await client.get('/api/v1/method/grunt.api.v1.workspace.get_counts', { params: { name } })
    return r.data.data
  },

  search: async (q: string, limit = 20): Promise<SearchResult[]> => {
    const r = await client.get('/api/v1/method/grunt.api.v1.search.search', { params: { q, limit } })
    return r.data.data
  },

}
