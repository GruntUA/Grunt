/**
 * «Стан системи» — the server fills every tab except «Браузер і офлайн»:
 * those checks (service worker, offline cache and queue, storage) can only
 * run here, in the browser that opened the report.
 *
 * @param {FormProxy} frm
 */

/** @param {FormProxy} frm */
async function _checkBrowser(frm) {
    const rows = await grunt.health.diagnose_browser()
    frm.set_value('browser_checks', rows.map((r, i) => ({ ...r, idx: i + 1 })))
    frm.mark_clean() // a live report — nothing to save
}

/** @param {FormProxy} frm */
function on_load(frm) {
    frm.hide_sidebar() // assignees, tags, follow — nothing to do with a live report
    _checkBrowser(frm)

    // A live report: nothing to print, share or link — and «Перевірити знову»
    // re-runs the browser checks too, so it replaces the plain refresh.
    for (const id of ['refresh', 'print', 'print_xlsx', 'print_pdf', 'print_html', 'open_new_tab', 'share', 'links', 'activity']) {
        frm.actions.remove(id)
    }

    frm.actions.add({
        id: 'recheck',
        label: __('Check again'),
        icon: 'refresh-cw',
        busy: (f) => f.is_loading,
        action: async (f) => {
            await f.reload()
            await _checkBrowser(f)
            grunt.show_alert(__('Check updated'), 'success')
        },
    })

    frm.actions.add({
        id: 'persist_storage',
        label: __('Persist browser storage'),
        icon: 'hard-drive',
        placement: 'menu',
        action: async (f) => {
            const ok = await grunt.health.persist_storage()
            grunt.show_alert(
                ok ? __('The browser will not delete offline data') : __('The browser declined the request (try installing the app as a PWA)'),
                ok ? 'success' : 'warning',
            )
            await _checkBrowser(f)
        },
    })

    frm.actions.add({
        id: 'copy_report',
        label: __('Copy report'),
        icon: 'clipboard-copy',
        placement: 'menu',
        action: async (f) => {
            try {
                await navigator.clipboard.writeText(JSON.stringify({ ...f.doc }, null, 2))
                grunt.show_alert(__('Report copied to the clipboard'), 'success')
            } catch (e) {
                grunt.show_alert(__('Clipboard unavailable:') + ' ' + e.message, 'error')
            }
        },
    })
}
