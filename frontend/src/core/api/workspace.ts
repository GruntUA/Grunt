import client from './client'

export interface WorkspaceLink {
  section: string
  type: 'DocType' | 'Report' | 'Page' | 'URL' | 'Divider'
  label: string
  icon: string
  link_to: string
  show_count: boolean
  count_filters?: string
  /** Key of this item's badge in the counts map (differs from link_to when filtered). */
  count_key?: string
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
  /** Pages offered on the app's home (home page first), only those the user may open. */
  dashboards: { name: string; label: string }[]
  items: WorkspaceLink[]
}

export interface SearchResult {
  doctype: string
  id: string
  name: string
  display_title: string
}

export interface AssignedTask {
  id: string
  description: string | null
  reference_doctype: string
  reference_id: string
  title: string
  due_date: string | null
  priority: string | null
  overdue: boolean
}

export interface UserNotification {
  name: string
  subject: string
  ref_doctype: string | null
  doc_id: string | null
  created_at: string
}

export interface MyWork {
  assigned: AssignedTask[]
  notifications: UserNotification[]
  counts: { assigned: number; overdue: number; unread: number }
}

export type OnboardingStepStatus = 'Pending' | 'Completed' | 'Skipped'

export interface OnboardingStep {
  step_id: string
  title: string
  description?: string | null
  action: string
  action_label?: string | null
  /** Where the button leads (`appUrl` link); `type: 'URL'` - a desk path or a full URL. */
  target: { type: string; name: string; id?: string; query?: Record<string, string> } | null
  status: OnboardingStepStatus
}

export interface FormTourStep {
  title: string
  description?: string | null
  /** The form field to point at, or `element` - a CSS selector; neither - a centred step. */
  fieldname?: string | null
  element?: string | null
}

export interface FormTour {
  name: string
  title: string
  auto_start: boolean
  /** The user has finished or closed it before. */
  taken: boolean
  steps: FormTourStep[]
}

export interface Onboarding {
  name: string
  title: string
  subtitle?: string | null
  app?: string | null
  success_message?: string | null
  documentation_url?: string | null
  steps: OnboardingStep[]
  done: number
  total: number
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

  getDocumentStats: async (): Promise<{ total: number; doctypes: number }> => {
    const r = await client.get('/api/v1/method/grunt.api.v1.workspace.get_document_stats')
    return r.data.data
  },

  getMyWork: async (): Promise<MyWork> => {
    const r = await client.get('/api/v1/method/grunt.api.v1.workspace.get_my_work')
    return r.data.data
  },

  search: async (q: string, limit = 20): Promise<SearchResult[]> => {
    const r = await client.get('/api/v1/method/grunt.api.v1.search.search', { params: { q, limit } })
    return r.data.data
  },

  getOnboardings: async (app?: string | null): Promise<Onboarding[]> => {
    const r = await client.get('/api/v1/method/grunt.site.onboarding.get_onboardings', { params: { app: app || undefined } })
    return r.data.data ?? []
  },

  markOnboardingStep: async (onboarding: string, stepId: string, status: OnboardingStepStatus): Promise<Onboarding> => {
    const r = await client.post('/api/v1/method/grunt.site.onboarding.mark_step', { onboarding, step_id: stepId, status })
    return r.data.data
  },

  hideOnboarding: async (onboarding: string): Promise<void> => {
    await client.post('/api/v1/method/grunt.site.onboarding.hide_onboarding', { onboarding })
  },

  getFormTours: async (doctype: string): Promise<FormTour[]> => {
    const r = await client.get('/api/v1/method/grunt.site.onboarding.get_form_tours', { params: { doctype } })
    return r.data.data ?? []
  },

  completeFormTour: async (tour: string): Promise<void> => {
    await client.post('/api/v1/method/grunt.site.onboarding.complete_form_tour', { tour })
  },
}
