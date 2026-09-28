import client from './client'

export interface FileItem {
    id: string
    url: string
    /** Small WebP preview (images, PDF first page), if the server made one. */
    thumbnail_url?: string | null
    filename: string
    content_type: string
    content_hash?: string | null
    size_bytes: number
    created_at: string | null
    uploaded_by: string
    attached_to_doctype?: string | null
    attached_to_id?: string | null
    /** Set by `upload` when byte-identical content was already stored. */
    deduped?: boolean
}

export type FileSortField = 'created_at' | 'file_name' | 'file_size'

export interface FileListParams {
    search?: string
    page?: number
    limit?: number
    /** Exact-match set on `content_type` (e.g. the document category). */
    contentTypes?: string[]
    /** Substring match on `content_type` (e.g. `image/` for "any image"). */
    contentTypeLike?: string
    attachedToDoctype?: string
    attachedToId?: string
    orderBy?: FileSortField
    order?: 'asc' | 'desc'
}

export const filesApi = {
    // The API returns `name` as the PK; the axios response interceptor adds
    // `id = name` recursively, so `FileItem.id` is always populated here.
    list: async (p: FileListParams = {}): Promise<{ items: FileItem[]; total: number }> => {
        const filters: Record<string, unknown> = {}
        if (p.contentTypes?.length) filters.content_type__in = p.contentTypes
        if (p.contentTypeLike) filters.content_type__ilike = p.contentTypeLike
        if (p.attachedToDoctype) filters.attached_to_doctype = p.attachedToDoctype
        if (p.attachedToId) filters.attached_to_id = p.attachedToId

        const params: Record<string, unknown> = {
            page: p.page ?? 1,
            limit: p.limit ?? 50,
        }
        if (p.search?.trim()) params.search = p.search.trim()
        if (Object.keys(filters).length) params.filters = JSON.stringify(filters)
        if (p.orderBy) params.order_by = p.orderBy
        if (p.order) params.order = p.order

        const res = await client.get(
            '/api/v1/method/grunt.storage.doctypes.File.file.get_list',
            { params },
        )
        return res.data.data
    },

    upload: async (file: File, opts?: { attachedToDoctype?: string; attachedToId?: string }): Promise<FileItem> => {
        const formData = new FormData()
        formData.append('file', file)
        if (opts?.attachedToDoctype) formData.append('attached_to_doctype', opts.attachedToDoctype)
        if (opts?.attachedToId) formData.append('attached_to_id', opts.attachedToId)
        const res = await client.post('/api/v1/method/grunt.storage.doctypes.File.file.upload', formData, {
            headers: { 'Content-Type': 'multipart/form-data' }
        })
        return res.data.data
    },

    getById: async (id: string): Promise<FileItem | null> => {
        const res = await client.get(`/api/v1/docs/File/${id}`)
        const doc = res.data.data
        return doc ? {
            id: doc.id,
            url: doc.file_url,
            filename: doc.file_name,
            content_type: doc.content_type,
            size_bytes: doc.file_size,
            created_at: doc.created_at,
            uploaded_by: doc.uploaded_by,
            attached_to_doctype: doc.attached_to_doctype,
            attached_to_id: doc.attached_to_id,
        } : null
    },

    delete: async (id: string): Promise<void> => {
        await client.post('/api/v1/method/grunt.storage.doctypes.File.file.remove', { file_id: id })
    },
}
