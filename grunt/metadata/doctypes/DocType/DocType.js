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

/**
 * Refresh title_field, image_field, and status_field options based on current fields list.
 * title_field / status_field — all non-layout fields; image_field — only
 * Image/Attach fields; kanban_column_field — only Select fields.
 */
function _refresh_field_selects(frm) {
    const LAYOUT_TYPES = new Set(['Tab', 'Section', 'Column', 'HTML', 'Heading'])
    const IMAGE_TYPES = new Set(['Image', 'Attach', 'AttachImage'])
    const DATE_TYPES = new Set(['Date', 'Datetime'])
    const NUMBER_TYPES = new Set(['Float', 'Int', 'Percent'])
    const TEXT_TYPES = new Set(['Data', 'Text', 'SmallText', 'LongText', 'Select', 'Link', 'Code', 'JSON'])

    const fields = frm.doc.fields || []
    const named = fields.filter(f => f.fieldname)
    const pick = pred => named.filter(pred).map(f => f.fieldname)

    const allFieldnames = pick(f => !LAYOUT_TYPES.has(f.fieldtype))
    const imageFieldnames = pick(f => IMAGE_TYPES.has(f.fieldtype))
    const selectFieldnames = pick(f => f.fieldtype === 'Select')
    const linkFieldnames = pick(f => f.fieldtype === 'Link')
    const dateFieldnames = pick(f => DATE_TYPES.has(f.fieldtype))
    const numberFieldnames = pick(f => NUMBER_TYPES.has(f.fieldtype))
    const textFieldnames = pick(f => TEXT_TYPES.has(f.fieldtype))

    const opt = names => '\n' + names.join('\n')
    frm.set_df_property('title_field', 'options', opt(allFieldnames))
    frm.set_df_property('search_fields', 'options', opt(textFieldnames))
    frm.set_df_property('image_field', 'options', opt(imageFieldnames))
    frm.set_df_property('status_field', 'options', opt(allFieldnames))
    frm.set_df_property('kanban_column_field', 'options', opt(selectFieldnames))
    frm.set_df_property('tree_parent_field', 'options', opt(linkFieldnames))
    frm.set_df_property('tree_title_field', 'options', opt(allFieldnames))
    frm.set_df_property('tree_as_of_date_field', 'options', opt(dateFieldnames))
    frm.set_df_property('tree_sort_by', 'options', opt(allFieldnames))
    frm.set_df_property('gantt_start_field', 'options', opt(dateFieldnames))
    frm.set_df_property('gantt_end_field', 'options', opt(dateFieldnames))
    frm.set_df_property('gantt_title_field', 'options', opt(allFieldnames))
    frm.set_df_property('gantt_progress_field', 'options', opt(numberFieldnames))
    frm.set_df_property('gantt_color_field', 'options', opt(selectFieldnames))
    frm.set_df_property('gantt_dependencies_field', 'options', opt(allFieldnames))
    frm.set_df_property('calendar_date_field', 'options', opt(dateFieldnames))
    frm.set_df_property('calendar_end_date_field', 'options', opt(dateFieldnames))
    frm.set_df_property('calendar_title_field', 'options', opt(allFieldnames))
}

async function on_load(frm) {
    // Populate title_field / image_field selects from current fields
    _refresh_field_selects(frm)

    // Load apps and populate selects
    try {
        const result = await grunt.api.get('/api/v1/docs/GruntInstalledApp')
        const apps = result?.data || []
        window._dtAppsCache = apps

        // Populate app options
        const appOptions = apps.map(a => a.name).join('\n')
        frm.set_df_property('app', 'options', appOptions)

        // For existing docs — reverse-lookup app from current module
        const currentModule = frm.get_value('module')
        if (currentModule) {
            const matchingApp = apps.find(a => (a.modules || []).includes(currentModule))
            if (matchingApp) {
                frm.set_value('app', matchingApp.name)
                frm.set_df_property('module', 'options', (matchingApp.modules || []).join('\n'))
                frm.set_df_property('module', 'description', '')
            }
        }

        // For new docs, make app and module required
        if (frm.is_new) {
            frm.toggle_reqd('app', true)
            frm.toggle_reqd('module', true)
        }
    } catch (e) {
        grunt.show_alert('Не вдалося завантажити список додатків', 'error')
    }
}

async function on_change(frm, fieldname) {
    // Refresh field selects whenever the fields table changes
    if (fieldname === 'fields') {
        _refresh_field_selects(frm)
        return
    }

    if (fieldname === 'status_field') {
        _seed_status_indicators(frm)
        return
    }

    if (fieldname !== 'app') return

    const selectedApp = frm.get_value('app')

    // Clear module when app is deselected
    if (!selectedApp) {
        frm.set_df_property('module', 'options', '')
        frm.set_value('module', '')
        return
    }

    let apps = window._dtAppsCache
    if (!apps || !apps.length) {
        try {
            const result = await grunt.api.get('/api/v1/docs/GruntInstalledApp')
            apps = result?.data || []
            window._dtAppsCache = apps
        } catch (e) {
            return
        }
    }

    const app = apps.find(a => a.name === selectedApp)
    if (app) {
        // Clear module selection, update options, remove hint
        frm.set_value('module', '')
        frm.set_df_property('module', 'options', (app.modules || []).join('\n'))
        frm.set_df_property('module', 'description', '')
    }
}

// Export for the executor
window.doc_type_on_load = on_load
window.doc_type_on_change = on_change

if (typeof on_load === 'function') { window.on_load = on_load }
if (typeof on_change === 'function') { window.on_change = on_change }

/** @param {ListViewProxy} listview */
function setup_list(listview) {
  listview.actions.update('add', { label: __('New DocType') })
}
