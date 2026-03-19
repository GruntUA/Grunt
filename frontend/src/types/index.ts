export interface DocField {
    fieldname: string
    label: string
    fieldtype: string
    required?: boolean
    in_list_view?: boolean
    hidden?: boolean
    read_only?: boolean
    options?: string
    // more properties as needed based on the Pydantic models
}

export interface DocType {
    name: string
    label: string
    module: string
    fields: DocField[]
    is_child?: boolean
    is_submittable?: boolean
    is_singleton?: boolean
    track_changes?: boolean
}

export interface StandardResponse<T> {
    data: T
    message?: string
}

export interface PaginationMeta {
    total: number
    limit: number
    offset: number
}

export interface StandardListResponse<T> {
    data: T[]
    meta: PaginationMeta
    message?: string
}

export interface DocTypeSyncResult {
    table_name: string
    status: string
    changes: string[]
}
