/**
 * «Стан системи» — the server fills every tab except «Браузер і офлайн»:
 * those checks (service worker, offline cache and queue, storage) can only
 * run here, in the browser that opened the report.
 *
 * @param {FormProxy} frm
 */

/** @param {FormProxy} frm */
function _renderDashboard(frm) {
    if (!frm.doc) return

    frm.dashboard.reset()

    const ok = Number(frm.doc.ok_count) || 0
    const warn = Number(frm.doc.warning_count) || 0
    const err = Number(frm.doc.error_count) || 0
    const total = ok + warn + err || 1

    // 1. Headline Banner
    if (err > 0) {
        frm.dashboard.set_headline(
            __('Увага: у системі виявлено критичні проблеми ({count}), що потребують втручання адміністратора.', { count: err }),
            'red'
        )
    } else if (warn > 0) {
        frm.dashboard.set_headline(
            __('Система функціонує, але виявлено {count} попереджень. Рекомендовано переглянути перевірки.', { count: warn }),
            'orange'
        )
    } else {
        frm.dashboard.set_headline(
            __('Всі компоненти системи працюють у штатному режимі. Помилок чи зауважень немає.'),
            'green'
        )
    }

    // 2. Stat indicators
    frm.dashboard.add_indicator(`${__('Добре')}: ${ok}`, 'green')
    frm.dashboard.add_indicator(`${__('Попередження')}: ${warn}`, warn > 0 ? 'orange' : 'gray')
    frm.dashboard.add_indicator(`${__('Проблеми')}: ${err}`, err > 0 ? 'red' : 'gray')

    // 3. Health Score progress bar (multi-segmented)
    const okPct = Math.round((ok / total) * 100)
    const warnPct = Math.round((warn / total) * 100)
    const errPct = Math.max(0, 100 - okPct - warnPct)

    frm.dashboard.add_progress(
        __('Індекс готовності системи'),
        [
            { title: __('Добре'), width: okPct, color: 'green' },
            { title: __('Попередження'), width: warnPct, color: 'orange' },
            { title: __('Проблеми'), width: errPct, color: 'red' },
        ],
        `${ok}/${total} (${okPct}%)`
    )

    // 4. Checks by category chart
    const checks = Array.isArray(frm.doc.checks) ? frm.doc.checks : []
    if (checks.length) {
        const catMap = new Map()
        for (const c of checks) {
            const cat = c.category || __('Інше')
            if (!catMap.has(cat)) catMap.set(cat, { ok: 0, issues: 0 })
            const entry = catMap.get(cat)
            if (c.status === 'OK') entry.ok += 1
            else entry.issues += 1
        }
        const shortCat = (cat) => {
            const map = {
                'Користувачі та безпека': 'Безпека',
                'Users and security': 'Security',
                'Фонові задачі': 'Фон. задачі',
                'Background jobs': 'Jobs',
                'Електронна пошта': 'Пошта',
                'Email': 'Email',
                'Залежності додатків': 'Залежності',
                'App dependencies': 'Deps',
                'Хмарне сховище': 'Хмара',
                'Cloud storage': 'Cloud',
            }
            return map[cat] || cat
        }

        const topCats = [...catMap.entries()]
            .sort((a, b) => (b[1].ok + b[1].issues) - (a[1].ok + a[1].issues))
            .slice(0, 6)

        if (topCats.length) {
            frm.dashboard.render_graph({
                title: __('Результати перевірок за категоріями'),
                type: 'bar',
                colors: ['#10b981', '#f59e0b'],
                data: {
                    labels: topCats.map(([cat]) => shortCat(cat)),
                    datasets: [
                        { name: __('Добре'), values: topCats.map(([, stats]) => stats.ok) },
                        { name: __('Зауваження'), values: topCats.map(([, stats]) => stats.issues) },
                    ],
                },
            })
        }
    }

    // 5. Related system DocTypes
    frm.dashboard.add_transactions({
        label: __('Пов’язані системні журнали'),
        items: ['ErrorLog', 'BackgroundJob', 'ScheduledJob', 'ActivityLog'],
    })
}

/** @param {FormProxy} frm */
async function _checkBrowser(frm) {
    const rows = await grunt.health.diagnose_browser()
    frm.set_value('browser_checks', rows.map((r, i) => ({ ...r, idx: i + 1 })))
    frm.mark_clean() // a live report — nothing to save
}

/** @param {FormProxy} frm */
function on_load(frm) {
    frm.hide_sidebar() // assignees, tags, follow — nothing to do with a live report
    _renderDashboard(frm)
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
            _renderDashboard(f)
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
