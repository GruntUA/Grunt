import client from './client'
import type { GruntDocument, StandardListResponse } from '@/types'

export interface WorkflowTransitionItem {
  action: string
  to_state: string
}

export interface BacklinkItem {
  source_doctype: string
  source_id: string
  link_fieldname: string
}

export interface ListParams {
  page?: number
  per_page?: number
  sort?: string
  order?: 'asc' | 'desc'
  search?: string
  fields?: string
  filters?: Record<string, string>
}

export const docsApi = {
  list: async (doctype: string, params: ListParams = {}): Promise<StandardListResponse<GruntDocument>> => {
    const { filters = {}, ...rest } = params
    const filterParams = Object.fromEntries(
      Object.entries(filters).map(([k, v]) => [`filter[${k}]`, v])
    )
    const r = await client.get(`/api/v1/docs/${doctype}`, {
      params: { ...rest, ...filterParams }
    })
    return r.data
  },

  get: (doctype: string, id: string): Promise<GruntDocument> =>
    client.get(`/api/v1/docs/${doctype}/${id}`)
      .then(r => r.data.data),

  create: (doctype: string, data: Record<string, unknown>): Promise<GruntDocument> =>
    client.post(`/api/v1/docs/${doctype}`, data)
      .then(r => r.data.data),

  update: (doctype: string, id: string, data: Record<string, unknown>): Promise<GruntDocument> =>
    client.put(`/api/v1/docs/${doctype}/${id}`, data)
      .then(r => r.data.data),

  delete: (doctype: string, id: string) =>
    client.delete(`/api/v1/docs/${doctype}/${id}`),

  bulkDelete: (doctype: string, ids: string[]): Promise<{ deleted: number; errors: string[] }> =>
    client.post(`/api/v1/docs/${doctype}/bulk-delete`, { ids })
      .then(r => r.data.data),

  getTransitions: (doctype: string, id: string): Promise<{ data: WorkflowTransitionItem[] }> =>
    client.get(`/api/v1/docs/${doctype}/${id}/transitions`).then(r => r.data),

  applyTransition: (doctype: string, id: string, action: string): Promise<{ success: boolean; data: GruntDocument }> =>
    client.post(`/api/v1/docs/${doctype}/${id}/transition`, { action }).then(r => r.data),

  getLinks: (doctype: string, id: string): Promise<BacklinkItem[]> =>
    client.get(`/api/v1/docs/${doctype}/${id}/links`).then(r => r.data.data ?? []),

  getAssignees: (doctype: string, id: string): Promise<GruntDocument[]> =>
    client.get(`/api/v1/docs/ToDo`, {
      params: { 'filter[reference_doctype]': doctype, 'filter[reference_id]': id, 'filter[status]': 'Open' }
    }).then(r => r.data.data ?? []),

  assign: (doctype: string, id: string, user: string): Promise<GruntDocument> =>
    client.post(`/api/v1/docs/ToDo`, {
      reference_doctype: doctype,
      reference_id: id,
      assigned_to: user,
      status: 'Open',
      description: `Assigned to ${user}`,
    }).then(r => r.data.data),

  getSharedWith: (doctype: string, id: string): Promise<GruntDocument[]> =>
    client.get(`/api/v1/docs/SharedWith`, {
      params: { 'filter[reference_doctype]': doctype, 'filter[reference_id]': id }
    }).then(r => r.data.data ?? []),

  share: (doctype: string, id: string, user: string, permission: 'Read' | 'Write' = 'Read'): Promise<GruntDocument> =>
    client.post(`/api/v1/docs/SharedWith`, {
      reference_doctype: doctype,
      reference_id: id,
      user,
      permission,
    }).then(r => r.data.data),

  unshare: (shareId: string): Promise<void> =>
    client.delete(`/api/v1/docs/SharedWith/${shareId}`).then(() => undefined),

  unassign: (todoId: string): Promise<void> =>
    client.delete(`/api/v1/docs/ToDo/${todoId}`).then(() => undefined),

  getTags: (doctype: string, id: string): Promise<GruntDocument[]> =>
    client.get(`/api/v1/docs/DocTag`, {
      params: { 'filter[reference_doctype]': doctype, 'filter[reference_id]': id }
    }).then(r => r.data.data ?? []),

  addTag: (doctype: string, id: string, tag: string): Promise<GruntDocument> =>
    client.post(`/api/v1/docs/DocTag`, {
      reference_doctype: doctype,
      reference_id: id,
      tag,
    }).then(r => r.data.data),

  removeTag: (tagId: string): Promise<void> =>
    client.delete(`/api/v1/docs/DocTag/${tagId}`).then(() => undefined),
}
