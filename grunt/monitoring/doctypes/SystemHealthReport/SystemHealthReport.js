/**
 * «Стан системи» — the server answers at once with a skeleton (every section
 * pending); this script then asks for every section in parallel
 * (grunt.monitoring.health.run_section — a request each, so a slow one, like
 * «Оновлення» asking the network, holds up only its own rows) and swaps each
 * one's server-rendered markup in as it arrives. «Браузер і офлайн» runs here,
 * in the browser that opened the report.
 *
 * @param {FormProxy} frm
 */

const METHOD = 'grunt.monitoring.health'
const STATUSES = ['OK', 'Warning', 'Error']

/** Results of the current run: section key -> rows; a new run drops a late answer of the previous one. */
let _run = { id: 0, rows: new Map(), pending: 0 }

/** Replace `<tbody data-health="key">` in an HTMLView field's markup. */
function _swap(frm, fieldname, key, html) {
    const tpl = document.createElement('template')
    tpl.innerHTML = String(frm.doc[fieldname] || '')
    const part = document.createElement('template')
    part.innerHTML = html
    const old = tpl.content.querySelector(`tbody[data-health="${key}"]`)
    const fresh = part.content.querySelector('tbody')
    if (old && fresh) old.replaceWith(fresh)
    frm.set_value(fieldname, tpl.innerHTML)
}

/** Markup for a section whose request failed (the server rendered nothing). */
function _failedHtml(kind, key, row) {
    const tbody = document.createElement('tbody')
    tbody.dataset.health = key
    for (const text of [row.category, `${row.value}: ${row.hint}`]) {
        const tr = tbody.insertRow()
        const cell = document.createElement(text === row.category ? 'th' : 'td')
        cell.colSpan = 4
        cell.textContent = text
        tr.append(cell)
    }
    if (kind === 'checks') return tbody.outerHTML
    const table = document.createElement('table')
    tbody.firstChild.remove()
    table.append(tbody)
    return table.outerHTML
}

/** Every server check row so far (sections of kind «checks»). */
function _checks(frm) {
    const keys = (frm.doc.sections || []).filter((s) => s.kind === 'checks').map((s) => s.key)
    return keys.flatMap((k) => _run.rows.get(k) || [])
}

/** @param {FormProxy} frm */
async function _runSections(frm) {
    const run = { id: _run.id + 1, rows: new Map(), pending: 0 }
    _run = run
    const sections = frm.doc.sections || []
    run.pending = sections.length
    _renderDashboard(frm)

    await Promise.all(sections.map(async ({ key, kind, label }) => {
        let result
        try {
            result = await grunt.call(`${METHOD}.run_section`, { key })
        } catch (e) {
            const failed = { category: label, check: label, status: 'Error', value: __('check failed'), hint: e.message }
            result = { key, rows: kind === 'checks' ? [failed] : [], html: _failedHtml(kind, key, failed) }
        }
        if (run !== _run) return
        run.rows.set(key, result.rows || [])
        run.pending -= 1
        if (result.html) {
            if (kind === 'items') frm.set_value(key, result.html)
            else _swap(frm, 'report', key, result.html)
        }
        if (!run.pending) {
            const tally = _tally(_checks(frm))
            frm.set_value('overall_status', tally.Error ? 'Error' : tally.Warning ? 'Warning' : 'OK')
        }
        frm.mark_clean() // a live report — nothing to save
        _renderDashboard(frm)
    }))
}

function _tally(rows) {
    const tally = Object.fromEntries(STATUSES.map((s) => [s, 0]))
    for (const r of rows) if (r.status in tally) tally[r.status] += 1
    return tally
}

/** @param {FormProxy} frm */
function _renderDashboard(frm) {
    if (!frm.doc) return

    frm.dashboard.reset()

    const checks = _checks(frm)
    const { OK: ok, Warning: warn, Error: err } = _tally(checks)
    const total = ok + warn + err || 1

    // 1. Headline Banner
    if (_run.pending) {
        frm.dashboard.set_headline(
            __('Checking… {done} of {total} sections ready', { done: (frm.doc.sections || []).length - _run.pending, total: (frm.doc.sections || []).length }),
            'gray'
        )
    } else if (err > 0) {
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
    if (frm.doc.checked_at) {
        frm.dashboard.add_indicator(`${__('Checked')}: ${new Date(frm.doc.checked_at).toLocaleString()}`, 'gray')
    }

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
                'Фреймворк і додатки': 'Додатки',
                'Framework and apps': 'Apps',
                'Середовища виконання': 'Середовища',
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
    _run.browser = rows
    frm.set_value('browser_report', await grunt.call(`${METHOD}.render_checks`, { rows }))
    frm.mark_clean() // a live report — nothing to save
}

/** @param {FormProxy} frm */
function on_load(frm) {
    frm.hide_sidebar() // assignees, tags, follow — nothing to do with a live report
    _runSections(frm)
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
            await Promise.all([_runSections(f), _checkBrowser(f)])
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
                const report = {
                    checked_at: f.doc.checked_at,
                    overall_status: f.doc.overall_status,
                    checks: _checks(f),
                    top_errors: _run.rows.get('top_errors') || [],
                    largest_tables: _run.rows.get('largest_tables') || [],
                    browser_checks: _run.browser || [],
                }
                await navigator.clipboard.writeText(JSON.stringify(report, null, 2))
                grunt.show_alert(__('Report copied to the clipboard'), 'success')
            } catch (e) {
                grunt.show_alert(__('Clipboard unavailable:') + ' ' + e.message, 'error')
            }
        },
    })
}
