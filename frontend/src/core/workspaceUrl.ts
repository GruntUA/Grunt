import { useAppStore } from '@/stores/app'

/**
 * In-app URLs. Every link into the workspace tree goes through here so it is
 * always the canonical `/app/<workspace>/…` form (never the bare
 * `/<workspace>/…` alias, and never a workspace-less `/<doctype>/…`, which the
 * router would misread as a workspace name).
 */

/** Workspace whose sidebar lists `doctype`; else the first workspace; else `grunt`. */
export function workspaceForDoctype(doctype?: string | null): string {
  const workspaces = useAppStore().workspaces
  if (doctype) {
    const owner = workspaces.find((ws) =>
      ws.items?.some((i) => i.type === 'DocType' && i.link_to === doctype),
    )
    if (owner) return owner.name
  }
  return workspaces[0]?.name || 'grunt'
}

/** `/app/<workspace>/<segments…>` — segments are joined as given (not encoded). */
export function workspaceUrl(workspace: string, ...segments: (string | number)[]): string {
  return ['/app', workspace, ...segments.map(String)].join('/')
}

/**
 * List (`id` omitted), form (`id`) or new-document (`id = 'new'`) URL for a
 * DocType. Without `workspace` the owning workspace is looked up by DocType.
 */
export function docUrl(doctype: string, id?: unknown, workspace?: string | null): string {
  const ws = workspace || workspaceForDoctype(doctype)
  const segments = [encodeURIComponent(doctype)]
  if (id !== undefined && id !== null && id !== '') segments.push(encodeURIComponent(String(id)))
  return workspaceUrl(ws, ...segments)
}
