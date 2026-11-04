/** Documents and REST API envelopes. */

export interface GruntDocument {
  /** The document's own DocType - every document (and child row) the API returns names it. */
  doctype?: string
  /** Synthesized from `name` by the API client shim - use `name` as the canonical PK. */
  id?: string
  name: string
  owner: string
  created_at: string
  modified_at: string
  modified_by: string
  [key: string]: unknown
}

export interface PaginationMeta {
  total: number
  page: number
  per_page: number
  pages: number
  /** Opaque cursor for keyset pagination - present when more rows exist */
  next_cursor?: string
  /**
   * Set by a virtual DocType backed by a live external source (Redis, an
   * API) when an empty list means "source unreachable", not "nothing
   * there" - e.g. BackgroundJob/BackgroundWorker without Redis configured.
   * ``unavailable_message`` is ready-to-display text from the backend.
   */
  unavailable?: boolean
  unavailable_message?: string
}

export interface StandardListResponse<T> {
  success: boolean
  data: T[]
  meta: PaginationMeta
}
