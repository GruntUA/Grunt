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

    frm.add_button('Перевірити знову', async () => {
        await frm.reload()
        await _checkBrowser(frm)
        grunt.show_alert('Перевірку оновлено', 'success')
    })

    frm.add_menu_item('Закріпити сховище браузера', async () => {
        const ok = await grunt.health.persist_storage()
        grunt.show_alert(
            ok ? 'Браузер не видалятиме офлайн-дані' : 'Браузер відхилив запит (спробуйте встановити застосунок як PWA)',
            ok ? 'success' : 'warning',
        )
        await _checkBrowser(frm)
    })

    frm.add_menu_item('Копіювати звіт', async () => {
        const report = { ...frm.doc }
        try {
            await navigator.clipboard.writeText(JSON.stringify(report, null, 2))
            grunt.show_alert('Звіт скопійовано в буфер обміну', 'success')
        } catch (e) {
            grunt.show_alert('Буфер обміну недоступний: ' + e.message, 'error')
        }
    })
}
