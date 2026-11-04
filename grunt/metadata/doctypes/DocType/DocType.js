/**
 * Client Script for DocType
 */

// Colour palette cycled through when auto-seeding status indicators.
const STATUS_COLORS = ['secondary', 'success', 'info', 'warn', 'danger', 'contrast', 'primary', 'default']

/**
 * When `status_field` points at a Select field and the indicators table is
 * still empty, pre-fill one row per option so the common case needs no typing.
 * Never clobbers a table the user has already edited.
 */
function _seed_status_indicators(frm) {
    if ((frm.doc.status_indicators || []).length) return

    const fname = frm.get_value('status_field')
    if (!fname) return

    const fld = (frm.doc.fields || []).find(f => f.fieldname === fname)
    if (!fld || fld.fieldtype !== 'Select' || !fld.options) return

    const values = String(fld.options).split('\n').map(s => s.trim()).filter(Boolean)
    if (!values.length) return

    frm.set_value('status_indicators', values.map((value, i) => ({
        value,
        color: STATUS_COLORS[i % STATUS_COLORS.length],
        icon: null,
        label: null,
    })))
}

// Views a DocType can open in: [value, icon, is it usable with these fields?]
// Mirrors each view's resolveField in frontend/src/components/views/*/index.ts.
const VIEWS = [
    ['list', 'LayoutList', () => true],
    ['report', 'Table2', () => true],
    ['gallery', 'Image', () => true],
    ['explorer', 'FolderOpen', ({ doc }) => {
        if (doc.default_view === 'explorer') return true
        return (doc.fields || []).some(f => f.fieldtype === 'Link' && f.options === 'FileFolder')
    }],
    ['kanban', 'LayoutGrid', ({ selects }) => selects.length > 0],
    ['calendar', 'CalendarDays', ({ dates }) => dates.length > 0],
    ['gantt', 'ChartGantt', ({ dates }) => dates.length > 1],
    ['tree', 'GitBranch', ({ doc }) => !!doc.is_tree],
    ['map', 'Map', ({ geo }) => geo.length > 0],
]

// Field-type groups offered by the field pickers below.
const LAYOUT_TYPES = ['Tab', 'Section', 'Column', 'HTML', 'Heading']
const GROUPS = {
    image: ['Image', 'Attach', 'AttachImage'],
    select: ['Select'],
    link: ['Link'],
    date: ['Date', 'Datetime'],
    number: ['Float', 'Int', 'Percent'],
    text: ['Data', 'LongText', 'Select', 'Link', 'Code', 'JSON'],
    check: ['Check'],
    geo: ['Geolocation'],
}

// Picker field -> group of fields it may point at ('all' = any non-layout field).
const PICKERS = {
    title_field: 'all',
    search_fields: 'text',
    image_field: 'image',
    status_field: 'all',
    kanban_column_field: 'select',
    tree_parent_field: 'link',
    tree_title_field: 'all',
    tree_as_of_date_field: 'date',
    tree_sort_by: 'all',
    gantt_start_field: 'date',
    gantt_end_field: 'date',
    gantt_title_field: 'all',
    gantt_progress_field: 'number',
    gantt_color_field: 'select',
    gantt_dependencies_field: 'all',
    calendar_date_field: 'date',
    calendar_end_date_field: 'date',
    calendar_title_field: 'all',
    is_published_field: 'check',
    retention_date_field: 'date',
}

const opt = names => '\n' + names.join('\n')

/** Refresh the options of every field picker (and default_view) from the fields table. */
function _refresh_field_selects(frm) {
    const named = (frm.doc.fields || []).filter(f => f.fieldname)
    const pick = types => named.filter(f => types.includes(f.fieldtype)).map(f => f.fieldname)

    const by = { all: named.filter(f => !LAYOUT_TYPES.includes(f.fieldtype)).map(f => f.fieldname) }
    for (const [group, types] of Object.entries(GROUPS)) by[group] = pick(types)

    for (const [picker, group] of Object.entries(PICKERS)) {
        frm.set_df_property(picker, 'options', opt(by[group]))
    }
    frm.set_df_property('sort_field', 'options', opt([...by.all, 'name', 'created_at', 'modified_at']))

    const available = { doc: frm.doc, selects: by.select, dates: by.date, geo: by.geo }
    const views = VIEWS.filter(([, , usable]) => usable(available))
    frm.set_df_property('default_view', 'options', opt(views.map(([value, icon]) => `${value}|${icon}`)))
}

/**
 * Installed apps with their modules. The script is re-evaluated on every event,
 * so the cache lives on window to survive between on_load and on_change.
 */
async function _get_apps() {
    if (!window._dtAppsCache?.length) {
        const result = await grunt.api.get('/api/v1/docs/GruntInstalledApp')
        window._dtAppsCache = result?.data || []
    }
    return window._dtAppsCache
}

function _set_module_options(frm, app) {
    frm.set_df_property('module', 'options', (app?.modules || []).join('\n'))
    frm.set_df_property('module', 'description', '')
}

async function on_load(frm) {
    _refresh_field_selects(frm)

    let apps
    try {
        apps = await _get_apps()
    } catch (e) {
        grunt.show_alert(__('Could not load the list of apps'), 'error')
        return
    }
    frm.set_df_property('app', 'options', apps.map(a => a.name).join('\n'))

    // Existing doc: reverse-lookup the app from its module
    const module = frm.get_value('module')
    const app = module && apps.find(a => (a.modules || []).includes(module))
    if (app) {
        frm.set_value('app', app.name)
        _set_module_options(frm, app)
    }

    if (frm.is_new) {
        frm.toggle_reqd('app', true)
        frm.toggle_reqd('module', true)
    }
}

async function on_change(frm, fieldname) {
    if (fieldname === 'fields' || fieldname === 'is_tree') return _refresh_field_selects(frm)
    if (fieldname === 'status_field') return _seed_status_indicators(frm)
    if (fieldname !== 'app') return

    const selected = frm.get_value('app')
    if (!selected) {
        frm.set_df_property('module', 'options', '')
        frm.set_value('module', '')
        return
    }

    let apps
    try {
        apps = await _get_apps()
    } catch (e) {
        return
    }
    const app = apps.find(a => a.name === selected)
    if (app) {
        frm.set_value('module', '')
        _set_module_options(frm, app)
    }
}

/** @param {ListViewProxy} listview */
function setup_list(listview) {
  listview.actions.update('add', { label: __('New DocType') })
}
