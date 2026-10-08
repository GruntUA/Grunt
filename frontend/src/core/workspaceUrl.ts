import { useAppStore } from '@/stores/app'
import { useDocTypeStore } from '@/stores/doctype'

/**
 * In-app URLs. Every link into the workspace tree goes through `appUrl` (or its
 * `docUrl` shorthand) so it is always the canonical `/app/<workspace>/…` form
 * (never the bare `/<workspace>/…` alias, and never a workspace-less
 * `/<doctype>/…`, which the router would misread as a workspace name).
 */

/** What a link points at - the same vocabulary as a workspace item (`type` + `link_to`). */
export type AppLinkType = 'Workspace' | 'DocType' | 'Report' | 'Page' | 'URL'

export interface AppLink {
  /** Defaults to `DocType`. */
  type?: AppLinkType | string
  /** Workspace / DocType / Report / Page name, or the address itself for `URL`. */
  name: string
  /** `DocType` only: document id, or `'new'` for the create form. Omitted = the list. */
  id?: unknown
  /** Owning workspace; looked up from the sidebars when omitted. */
  workspace?: string | null
  /** Query string; null / undefined / '' values are dropped. */
  query?: Record<string, unknown> | null
}

/** Workspace whose sidebar lists `name` of this `type`; else the first workspace; else `grunt`. */
export function workspaceFor(type: string, name?: string | null): string {
  const workspaces = useAppStore().workspaces
  if (name) {
    const owner = workspaces.find((ws) => ws.items?.some((i) => i.type === type && i.link_to === name))
    if (owner) return owner.name
  }
  return workspaces[0]?.name || 'grunt'
}

/** Whether `doctype` is a singleton, judged from metadata already loaded on the client. */
export function isSingletonDoctype(doctype: string): boolean {
  const dtStore = useDocTypeStore()
  const known = dtStore.cache.get(doctype) ?? dtStore.doctypes.find((d) => d.name === doctype)
  if (known) return !!known.is_singleton
  return useAppStore().workspaces.some((ws) =>
    ws.items?.some((i) => i.type === 'DocType' && i.link_to === doctype && i.is_singleton),
  )
}

function withQuery(path: string, query?: Record<string, unknown> | null): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== null && value !== undefined && value !== '') params.append(key, String(value))
  }
  const qs = params.toString()
  return qs ? `${path}?${qs}` : path
}

/**
 * URL of anything a link can point at:
 *
 *   appUrl({ type: 'Workspace', name: 'letter' })        -> /app/letter
 *   appUrl({ name: 'ToDo' })                             -> /app/<ws>/ToDo
 *   appUrl({ name: 'ToDo', id: 't1' })                   -> /app/<ws>/ToDo/t1
 *   appUrl({ name: 'ToDo', id: 'new' })                  -> /app/<ws>/ToDo/new
 *   appUrl({ type: 'Report', name: 'Monthly' })          -> /app/<ws>/report/Monthly
 *   appUrl({ type: 'Page', name: 'inventory-home' })     -> /app/<ws>/page/inventory-home
 *   appUrl({ type: 'URL', name: 'https://…' })           -> https://… (as is)
 *
 * A singleton's only document lives at the short `/app/<ws>/<DocType>` URL,
 * whatever its id.
 */
export function appUrl(link: AppLink): string {
  const type = link.type || 'DocType'
  if (type === 'URL') return link.name
  if (type === 'Workspace') return withQuery(`/app/${encodeURIComponent(link.name)}`, link.query)

  const ws = encodeURIComponent(link.workspace || workspaceFor(type, link.name))
  const name = encodeURIComponent(link.name)
  let path: string
  if (type === 'Report') path = `/app/${ws}/report/${name}`
  else if (type === 'Page') path = `/app/${ws}/page/${name}`
  else {
    path = `/app/${ws}/${name}`
    const { id } = link
    const hasId = id !== undefined && id !== null && id !== ''
    if (hasId && (String(id) === 'new' || !isSingletonDoctype(link.name))) {
      path += `/${encodeURIComponent(String(id))}`
    }
  }
  return withQuery(path, link.query)
}

/** Shorthand for the commonest link: a DocType list (`id` omitted), form, or `'new'` form. */
export function docUrl(doctype: string, id?: unknown, workspace?: string | null): string {
  return appUrl({ name: doctype, id, workspace })
}
