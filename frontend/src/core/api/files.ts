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
    /** The folder an upload went to (`upload`). */
    folder?: string | null
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
    /** Files filed in this folder (FileFolder). */
    folder?: string
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
        if (p.folder) filters.folder = p.folder

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

    upload: async (
        file: File,
        opts?: { attachedToDoctype?: string; attachedToId?: string; folder?: string; isPublic?: boolean },
    ): Promise<FileItem> => {
        const formData = new FormData()
        formData.append('file', file)
        if (opts?.attachedToDoctype) formData.append('attached_to_doctype', opts.attachedToDoctype)
        if (opts?.attachedToId) formData.append('attached_to_id', opts.attachedToId)
        if (opts?.folder) formData.append('folder', opts.folder)
        if (opts?.isPublic !== undefined) formData.append('is_public', String(opts.isPublic))
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

    /** The current user's home folder («My files»), created on first use. */
    homeFolder: async (): Promise<{ name: string; folder_name: string }> => {
        const res = await client.get('/api/v1/method/grunt.storage.doctypes.FileFolder.file_folder.get_home_folder')
        return res.data.data
    },

    /** Bytes used in a personal space and its quota (`null` - unlimited). */
    storageUsage: async (user?: string): Promise<{ used: number; quota: number | null }> => {
        const res = await client.get(
            '/api/v1/method/grunt.storage.doctypes.FileFolder.file_folder.get_storage_usage',
            { params: user ? { user } : {} },
        )
        return res.data.data
    },

    /** Download a file from the internet into a folder (server-side, public links only). */
    uploadFromUrl: async (url: string, folder?: string): Promise<FileItem> => {
        const res = await client.post(
            '/api/v1/method/grunt.storage.doctypes.File.file.upload_from_url',
            { url, folder },
        )
        return res.data.data
    },

    /** Copy files and folders (with their contents) into a folder - no new disk space. */
    copyItems: async (target: string, items: { files: string[]; folders: string[] }): Promise<number> => {
        const res = await client.post(
            '/api/v1/method/grunt.storage.doctypes.FileFolder.file_folder.copy_items',
            { target, ...items },
        )
        return res.data.data.copied
    },

    /** Delete files and folders - a folder together with everything in it (to the trash). */
    deleteItems: async (items: { files: string[]; folders: string[] }): Promise<number> => {
        const res = await client.post(
            '/api/v1/method/grunt.storage.doctypes.FileFolder.file_folder.delete_items',
            items,
        )
        return res.data.data.deleted
    },

    delete: async (id: string): Promise<void> => {
        await client.post('/api/v1/method/grunt.storage.doctypes.File.file.remove', { file_id: id })
    },
}
