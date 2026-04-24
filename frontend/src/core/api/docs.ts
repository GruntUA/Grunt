import client from './client'
import type { ActiveFilter, GruntDocument, StandardListResponse } from '@/types'

export interface WorkflowTransitionItem {
  action: string
  to_state: string
}

export interface CommentItem {
  id: string
  content: string
  comment_type: string
  user: string
  created_at: string | null
}

export interface TimelineItem {
  type: 'activity' | 'comment'
  id: string
  action?: string
  content?: string
  comment_type?: string
  user: string
  details?: Record<string, unknown> | null
  created_at: string | null
}

export interface BacklinkItem {
  source_doctype: string
  source_id: string
  link_fieldname: string
}

// Maps FilterBar display operators to backend query suffixes
export const OP_MAP: Record<string, string> = {
  '=': 'eq', '!=': 'ne', 'like': 'ilike',
  '>': 'gt', '<': 'lt', '>=': 'gte', '<=': 'lte',
}

/** Convert ActiveFilter[] to raw backend filter object: { "fieldname__op": "value" } */
export function filtersToRaw(filters: ActiveFilter[]): Record<string, string> {
  const raw: Record<string, string> = {}
  for (const f of filters) {
    raw[`${f.fieldname}__${OP_MAP[f.op] ?? 'eq'}`] = f.value
  }
  return raw
}

export interface ListParams {
  page?: number
  per_page?: number
  sort?: string
  order?: 'asc' | 'desc'
  search?: string
  fields?: string
  filters?: ActiveFilter[]
  /** Raw backend filters — keys may already contain __op suffixes (e.g. { 'date__lte': '2024-01-31' }) */
  rawFilters?: Record<string, string>
  /** Opaque cursor for keyset pagination (replaces page-based OFFSET) */
  cursor?: string
}

export interface LinkSearchItem {
  id: string
  name: string
  title: string
  subtitle: string | null
}

export const docsApi = {
  linkSearch: async (
    doctype: string,
    q: string,
    filters: Record<string, string> = {},
    pageLength = 10,
  ): Promise<LinkSearchItem[]> => {
    const r = await client.get(`/api/v1/docs/${doctype}/link_search`, {
      params: { q, filters: JSON.stringify(filters), page_length: pageLength },
    })
    return r.data.data ?? []
  },

  list: async (doctype: string, params: ListParams = {}): Promise<StandardListResponse<GruntDocument>> => {
    const { filters = [], rawFilters = {}, sort, order, ...rest } = params
    const filterParams: Record<string, string> = {}
    for (const f of filters) {
      const backendOp = OP_MAP[f.op] ?? 'eq'
      filterParams[`filter[${f.fieldname}__${backendOp}]`] = f.value
    }
    for (const [k, v] of Object.entries(rawFilters)) {
      filterParams[`filter[${k}]`] = v
    }
    const r = await client.get(`/api/v1/docs/${doctype}`, {
      params: {
        ...rest,
        ...(sort ? { sort_by: sort } : {}),
        ...(order ? { sort_order: order } : {}),
        ...filterParams,
      },
    })
    return r.data
  },

  get: <T extends GruntDocument = GruntDocument>(
    doctype: string,
    id: string,
    options?: { expand?: string[] | string },
  ): Promise<T> =>
    client.get(`/api/v1/docs/${doctype}/${id}`, {
      params: options?.expand
        ? {
          expand: Array.isArray(options.expand)
            ? options.expand.join(',')
            : options.expand,
        }
        : undefined,
    })
      .then(r => r.data.data as T),

  create: <T extends GruntDocument = GruntDocument>(
    doctype: string,
    data: Record<string, unknown>,
  ): Promise<T> =>
    client.post(`/api/v1/docs/${doctype}`, data)
      .then(r => r.data.data as T),

  update: <T extends GruntDocument = GruntDocument>(
    doctype: string,
    id: string,
    data: Record<string, unknown>,
  ): Promise<T> =>
    client.put(`/api/v1/docs/${doctype}/${id}`, data)
      .then(r => r.data.data as T),

  delete: (doctype: string, id: string) =>
    client.delete(`/api/v1/docs/${doctype}/${id}`),

  bulkDelete: (
    doctype: string,
    ids: string[],
    options?: { deleteAll?: boolean; rawFilters?: Record<string, string>; search?: string }
  ): Promise<{ started: boolean; total: number }> => {
    const body = options?.deleteAll
      ? { delete_all: true, filters: options.rawFilters ?? {}, search: options.search ?? null }
      : { ids }
    return client.post(`/api/v1/docs/${doctype}/bulk-delete`, body).then(r => r.data.data)
  },

  getTransitions: (doctype: string, id: string): Promise<{ data: WorkflowTransitionItem[] }> =>
    client.get(`/api/v1/docs/${doctype}/${id}/transitions`).then(r => r.data),

  applyTransition: (doctype: string, id: string, action: string): Promise<{ success: boolean; data: GruntDocument }> =>
    client.post(`/api/v1/docs/${doctype}/${id}/transition`, { action }).then(r => r.data),

  getLinks: (doctype: string, id: string): Promise<BacklinkItem[]> =>
    client.get(`/api/v1/docs/${doctype}/${id}/links`).then(r => r.data.data ?? []),

  getTree: async (doctype: string): Promise<any[]> => {
    const r = await client.get(`/api/v1/docs/${doctype}/tree`)
    return r.data.data ?? []
  },

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

  // ── Comments ────────────────────────────────────────────────────────────

  getComments: (doctype: string, id: string): Promise<CommentItem[]> =>
    client.get(`/api/v1/docs/${doctype}/${id}/comments`).then(r => r.data.data ?? []),

  addComment: (doctype: string, id: string, content: string): Promise<CommentItem> =>
    client.post(`/api/v1/docs/${doctype}/${id}/comments`, { content }).then(r => r.data.data),

  deleteComment: (doctype: string, id: string, commentId: string): Promise<void> =>
    client.delete(`/api/v1/docs/${doctype}/${id}/comments/${commentId}`).then(() => undefined),

  // ── Bookmarks ────────────────────────────────────────────────────────────

  getBookmark: (doctype: string, id: string): Promise<GruntDocument | null> =>
    client.get(`/api/v1/docs/${doctype}/${id}/bookmark`).then(r => r.data.data ?? null),

  addBookmark: (doctype: string, id: string, title?: string): Promise<GruntDocument> =>
    client.post(`/api/v1/docs/${doctype}/${id}/bookmark`, { title: title ?? '' }).then(r => r.data.data),

  removeBookmark: (doctype: string, id: string): Promise<void> =>
    client.delete(`/api/v1/docs/${doctype}/${id}/bookmark`).then(() => undefined),

  // ── Timeline ─────────────────────────────────────────────────────────────

  getTimeline: (doctype: string, id: string): Promise<TimelineItem[]> =>
    client.get(`/api/v1/docs/${doctype}/${id}/timeline`).then(r => r.data.data ?? []),

  // ── Bulk update ──────────────────────────────────────────────────────────

  rename: <T extends GruntDocument = GruntDocument>(doctype: string, id: string, newId: string): Promise<T> =>
    client.post(`/api/v1/docs/${doctype}/${id}/rename`, { new_name: newId })
      .then(r => r.data.data as T),

  bulkUpdate: (doctype: string, ids: string[], field: string, value: unknown): Promise<{ updated: number; errors: string[] }> =>
    client.post(`/api/v1/docs/${doctype}/bulk-update`, { ids, field, value }).then(r => r.data.data),
}
