import client from './client'

/** "*" - settings not tied to a DocType (recent documents). */
export const ANY_DOCTYPE = '*'

/** The current user's list settings on the server (grunt/api/v1/view_settings.py). */
export const viewSettingsApi = {
  /** `{view: settings}` of the current user for `doctype`. */
  get: async (doctype: string): Promise<Record<string, unknown>> => {
    const r = await client.get('/api/v1/method/grunt.api.v1.view_settings.get_view_settings', {
      params: { doctype },
    })
    return (r.data.data ?? {}) as Record<string, unknown>
  },

  /** Store one view's settings; `null` - back to the defaults. */
  save: async (doctype: string, view: string, settings: unknown): Promise<void> => {
    await client.post('/api/v1/method/grunt.api.v1.view_settings.save_view_settings', {
      doctype,
      view,
      settings,
    })
  },

  /** "Save as default for all" - the DocType's own list defaults (manage_doctypes). */
  saveListDefaults: async (
    doctype: string,
    defaults: {
      columns?: string[]
      sort_field?: string
      sort_order?: 'asc' | 'desc'
      default_view?: string
      quick_filters?: string[]
    },
  ): Promise<void> => {
    await client.post('/api/v1/method/grunt.api.v1.view_settings.save_list_defaults', { doctype, ...defaults })
  },
}
