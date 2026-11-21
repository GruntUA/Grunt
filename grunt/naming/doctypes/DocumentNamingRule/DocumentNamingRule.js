/**
 * DocumentNamingRule — the next name the rule would give, and its series counter.
 *
 * @param {FormProxy} frm
 */

const NAMING = 'grunt.api.v1.naming'

function _escape(text) {
    return String(text).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`)
}

async function _preview(frm) {
    if (!frm.doc.document_type || !frm.doc.autoname) return null
    return grunt.call(`${NAMING}.preview`, {
        doctype: frm.doc.document_type,
        pattern: frm.doc.autoname,
    })
}

/** @param {FormProxy} frm */
async function _show_next_name(frm) {
    let p
    try {
        p = await _preview(frm)
    } catch (e) {
        frm.dashboard.clear_headline()
        return
    }
    if (p && p.next) {
        frm.dashboard.set_headline(_escape(`${__('Next name')}: ${p.next}`), 'blue')
    } else if (p && p.fields && p.fields.length) {
        const labels = p.fields.map((f) => f.label).join(', ')
        frm.dashboard.set_headline(
            _escape(__('Each value of {fields} has its own count').replace('{fields}', labels)),
            'gray',
        )
    } else {
        frm.dashboard.clear_headline()
    }
}

/** @param {FormProxy} frm */
async function _edit_counter(frm) {
    const p = await _preview(frm)
    let prefix = p && p.prefix
    if (!prefix) {
        prefix = await grunt.prompt({
            title: __('Series counter'),
            label: __('Series prefix — the name up to the number, e.g. ВХ-2026-'),
        })
        if (!prefix) return
    }
    const now = prefix === (p && p.prefix) ? p.current : await grunt.call(`${NAMING}.counter`, { prefix })
    const value = await grunt.prompt({
        title: __('Series counter'),
        label: __('Last number given out in “{prefix}” (now {current}). The next document gets the one after it.')
            .replace('{prefix}', prefix)
            .replace('{current}', String(now ?? 0)),
        fieldtype: 'Int',
    })
    if (value === null || value === undefined || String(value).trim() === '') return
    await grunt.call(`${NAMING}.set_counter`, { prefix, current: Number(value) })
    grunt.show_alert(__('Counter updated'), 'success')
    await _show_next_name(frm)
}

/** @param {FormProxy} frm */
export function on_load(frm) {
    _show_next_name(frm)
}

/**
 * @param {FormProxy} frm
 * @param {string} fieldname
 */
export function on_change(frm, fieldname) {
    if (fieldname === 'naming_counter') return _edit_counter(frm)
    if (fieldname === 'autoname' || fieldname === 'document_type') return _show_next_name(frm)
}
