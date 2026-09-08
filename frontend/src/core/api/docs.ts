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

export interface DeleteImpactGroup {
  doctype: string | null
  label: string
  field: string | null
  field_label: string | null
  count: number
  in_child: boolean
  parent_doctype: string | null
}
export interface DeleteImpact {
  total: number
  groups: DeleteImpactGroup[]
}

export interface SidebarAssignee {
  name: string
  assigned_to: string
  description: string | null
  created_at: string | null
  status: string | null
  priority: string | null
  due_date: string | null
  is_overdue: boolean
}
export interface SidebarShare { name: string; user: string; permission: 'Read' | 'Write' }
export interface SidebarTag { name: string; tag: string }

export interface SidebarPerson { name: string; avatar: string | null }

export interface SidebarBundle {
  assignees: SidebarAssignee[]
  shares: SidebarShare[]
  tags: SidebarTag[]
  backlinks: BacklinkItem[]
  bookmark: GruntDocument | null
  /** email → display name + avatar, for everyone referenced above */
  people: Record<string, SidebarPerson>
}

// Maps FilterBar display operators to backend query suffixes
/**
 * A ToDo created without a task note carries auto-generated boilerplate as its
 * description: `assign()` below writes "Assigned to <email>"; backend auto-rules
 * write "Призначено: <doctype> <id>". Either should read as "no note".
 */
export const assignmentPlaceholder = (user: string): string => `Assigned to ${user}`

const ASSIGNMENT_PLACEHOLDER_RE = /^(Assigned to \S+|Призначено:.*)$/

export function isAssignmentPlaceholder(description: string | null | undefined): boolean {
  return ASSIGNMENT_PLACEHOLDER_RE.test((description ?? '').trim())
}

export const OP_MAP: Record<string, string> = {
  '=': 'eq', '!=': 'ne', 'like': 'ilike',
  '>': 'gt', '<': 'lt', '>=': 'gte', '<=': 'lte',
  'child_of': 'child_of',
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
  /**
   * Fast filter values in backend format { 'field__op': 'value' }.
   * Sent as quick_filter[...] params; explicit filter[...] take precedence on the backend.
   */
  quickFilters?: Record<string, string>
  /** Opaque cursor for keyset pagination (replaces page-based OFFSET) */
  cursor?: string
}

export interface LinkSearchFieldValue {
  fieldname: string
  label: string
  value: string
}

export interface LinkSearchItem {
  id: string
  name: string
  title: string
  subtitle: string | null
  /** Every configured `search_field` (label + value), minus the one shown as the title. */
  fields?: LinkSearchFieldValue[]
}

export const docsApi = {
  linkSearch: async (
    doctype: string,
    search: string,
    filters: Record<string, string | string[]> = {},
    perPage = 10,
  ): Promise<LinkSearchItem[]> => {
    const r = await client.get('/api/v1/method/grunt.document.base.Document.link_search', {
      params: { doctype, search, filters: JSON.stringify(filters), per_page: perPage },
    })
    return r.data.data ?? []
  },

  list: async (doctype: string, params: ListParams = {}): Promise<StandardListResponse<GruntDocument>> => {
    const { filters = [], rawFilters = {}, quickFilters = {}, sort, order, ...rest } = params
    const filterParams: Record<string, string> = {}
    // Fast filters have lower precedence — sent first so backend override logic applies
    for (const [k, v] of Object.entries(quickFilters)) {
      filterParams[`quick_filter[${k}]`] = v
    }
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

  delete: (doctype: string, id: string, replaceWith?: string) =>
    client.delete(`/api/v1/docs/${doctype}/${id}`, {
      params: replaceWith ? { replace_with: replaceWith } : undefined,
    }),

  bulkDelete: (
    doctype: string,
    ids: string[],
    options?: { deleteAll?: boolean; rawFilters?: Record<string, string>; search?: string; fast?: boolean; replaceWith?: string }
  ): Promise<{ started: boolean; total: number }> => {
    const body = options?.deleteAll
      ? { doctype, delete_all: true, filters: options.rawFilters ?? {}, search: options.search ?? null, fast: options.fast ?? false }
      : { doctype, ids, replace_with: options?.replaceWith ?? null }
    return client.post('/api/v1/method/grunt.api.v1.docs.crud.bulk_delete', body)
      .then(r => r.data.data)
  },

  /** What still references these documents — the impact of deleting them. */
  getDeleteImpact: (doctype: string, ids: string[]): Promise<DeleteImpact> =>
    client.post('/api/v1/method/grunt.document.base.Document.get_delete_impact', {
      doctype, doc_ids: ids,
    }).then(r => r.data.data),

  getTransitions: (doctype: string, id: string): Promise<{ data: WorkflowTransitionItem[] }> =>
    client.get('/api/v1/method/grunt.document.base.Document.get_workflow_transitions', {
      params: { doctype, doc_id: id },
    }).then(r => r.data),

  applyTransition: (doctype: string, id: string, action: string): Promise<{ success: boolean; data: GruntDocument }> =>
    client.post('/api/v1/method/grunt.document.base.Document.apply_workflow_transition', {
      doctype, doc_id: id, action,
    }).then(r => r.data),

  getLinks: (doctype: string, id: string): Promise<BacklinkItem[]> =>
    client.get('/api/v1/method/grunt.document.base.Document.get_backlinks', {
      params: { doctype, doc_id: id },
    }).then(r => r.data.data ?? []),

  getSidebar: (doctype: string, id: string): Promise<SidebarBundle> =>
    client.get('/api/v1/method/grunt.document.base.Document.get_sidebar', {
      params: { doctype, doc_id: id },
    }).then(r => r.data.data),

  getTree: async (
    doctype: string,
    params?: {
      as_of?: string
      quickFilters?: Record<string, string>
      filters?: ActiveFilter[]
      search?: string
      sort_by?: string
      sort_order?: 'asc' | 'desc'
    },
  ): Promise<any[]> => {
    // quick_filter[...] takes lower precedence than an explicit filter[...] for
    // the same key — merge fast filters first so filters can override them.
    const merged: Record<string, string> = { ...(params?.quickFilters ?? {}) }
    for (const f of params?.filters ?? []) {
      const backendOp = OP_MAP[f.op] ?? 'eq'
      merged[`${f.fieldname}__${backendOp}`] = f.value
    }
    const queryParams: Record<string, string> = { doctype }
    if (params?.as_of) queryParams.as_of = params.as_of
    if (params?.search?.trim()) queryParams.search = params.search.trim()
    if (params?.sort_by) queryParams.sort_by = params.sort_by
    if (params?.sort_order) queryParams.sort_order = params.sort_order
    if (Object.keys(merged).length) queryParams.filters = JSON.stringify(merged)

    const r = await client.get('/api/v1/method/grunt.document.base.Document.get_tree', {
      params: queryParams,
    })
    return r.data.data ?? []
  },

  assign: (doctype: string, id: string, user: string, description?: string): Promise<GruntDocument> =>
    client.post(`/api/v1/docs/ToDo`, {
      reference_doctype: doctype,
      reference_id: id,
      assigned_to: user,
      status: 'Open',
      description: description?.trim() || assignmentPlaceholder(user),
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
    client.get('/api/v1/method/grunt.document.base.Document.get_comments', {
      params: { doctype, doc_id: id },
    }).then(r => r.data.data ?? []),

  addComment: (doctype: string, id: string, content: string): Promise<CommentItem> =>
    client.post('/api/v1/method/grunt.document.base.Document.add_comment', {
      doctype, doc_id: id, content,
    }).then(r => r.data.data),

  deleteComment: (doctype: string, id: string, commentId: string): Promise<void> =>
    client.post('/api/v1/method/grunt.document.base.Document.delete_comment', {
      doctype, doc_id: id, comment_id: commentId,
    }).then(() => undefined),

  // ── Bookmarks ────────────────────────────────────────────────────────────

  getBookmark: (doctype: string, id: string): Promise<GruntDocument | null> =>
    client.get('/api/v1/method/grunt.document.base.Document.get_bookmark', {
      params: { doctype, doc_id: id },
    }).then(r => r.data.data ?? null),

  addBookmark: (doctype: string, id: string, title?: string): Promise<GruntDocument> =>
    client.post('/api/v1/method/grunt.document.base.Document.add_bookmark', {
      doctype, doc_id: id, title: title ?? '',
    }).then(r => r.data.data),

  removeBookmark: (doctype: string, id: string): Promise<void> =>
    client.post('/api/v1/method/grunt.document.base.Document.remove_bookmark', {
      doctype, doc_id: id,
    }).then(() => undefined),

  // ── Timeline ─────────────────────────────────────────────────────────────

  getTimeline: (doctype: string, id: string): Promise<TimelineItem[]> =>
    client.get('/api/v1/method/grunt.document.base.Document.get_timeline', {
      params: { doctype, doc_id: id },
    }).then(r => r.data.data ?? []),

  // ── Seen / views (track_seen / track_views) ─────────────────────────────

  getViewInfo: (doctype: string, id: string): Promise<{ seen: string[]; views: number; viewers: number }> =>
    client.get('/api/v1/method/grunt.activity.get_view_info', {
      params: { doctype, doc_id: id },
    }).then(r => r.data.data ?? { seen: [], views: 0, viewers: 0 }),

  // ── Bulk update ──────────────────────────────────────────────────────────

  rename: <T extends GruntDocument = GruntDocument>(doctype: string, id: string, newId: string): Promise<T> =>
    client.post('/api/v1/method/grunt.api.v1.docs.crud.rename', {
      doctype, doc_id: id, new_name: newId,
    }).then(r => r.data.data as T),

  bulkUpdate: (doctype: string, ids: string[], field: string, value: unknown): Promise<{ updated: number; errors: string[] }> =>
    client.post('/api/v1/method/grunt.api.v1.docs.crud.bulk_update', {
      doctype, ids, field, value,
    }).then(r => r.data.data),
}
