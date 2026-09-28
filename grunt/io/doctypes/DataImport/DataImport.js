// DataImport — Client Script

// ── Lifecycle hooks ──────────────────────────────────────────────────────────

function on_load(frm) {
  _addButtons(frm)
  if (!frm.is_new) _renderResultBanner(frm)
}

function on_change(frm, fieldname) {
  if (fieldname === 'status') _refreshStatusBanner(frm)
}

// ── Buttons ──────────────────────────────────────────────────────────────────

const _isDone = (f) => ['Success', 'Partial Success', 'Failed'].includes(f.doc.status)
const _isPending = (f) => !f.doc.status || f.doc.status === 'Pending'

function _addButtons(frm) {
  frm.actions.add({
    id: 'run_import',
    label: 'Run import',
    icon: 'play',
    variant: 'default',
    visible: (f) => !f.is_new && (_isPending(f) || _isDone(f)),
    action: (f) => _runImport(f),
  })
  frm.actions.add({
    id: 'reset_import',
    label: 'Reset',
    variant: 'secondary',
    visible: (f) => !f.is_new && _isDone(f),
    action: (f) => _reset(f),
  })
}

// ── Run ──────────────────────────────────────────────────────────────────────

async function _runImport(frm) {
  const id = frm.doc_id || frm.get_value('id') || frm.get_value('name')
  if (!id) return

  const mapping = frm.get_value('mapping')
  const hasMapping = mapping && Object.values(
    typeof mapping === 'string' ? JSON.parse(mapping) : mapping
  ).some(Boolean)

  if (!hasMapping) {
    grunt.show_alert(__('Set up the column mapping first'), 'warning')
    return
  }

  const dryRun = frm.get_value('dry_run')
  const label = dryRun ? __('Run validation (without writing)?') : __('Run the data import?')
  if (!await grunt.confirm(label)) return

  // Save first so the backend reads the current mapping from DB
  await frm.save()

  const btn = _findBtn(__('Run import'))
  if (btn) { btn.disabled = true; btn.textContent = '⏳ ' + __('Starting...') }

  // Show progress bar before the request so it's visible even if the task finishes fast
  const progressEl = _createProgressBar()

  const offProgress = grunt.on_progress(({ processed = 0, total = 0 }) => {
    const pct = total > 0 ? Math.round((processed / total) * 100) : 0
    _updateProgressBar(progressEl, pct, processed, total)
  })

  const offChange = grunt.onMessage('doc_change', async (data) => {
    offProgress()
    offChange()
    progressEl.remove()
    frm.reload()  // fire-and-forget — just refreshes the form in background
    _renderResultBanner(frm, data)
  })

  try {
    const resp = await fetch(
      `/api/v1/method/grunt.api.v1.data_import.run_import_job`,
      {
        method: 'POST',
        headers: _authHeaders(),
        body: JSON.stringify({ data_import_id: id }),
      }
    )
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      throw new Error(err?.error?.message || `HTTP ${resp.status}`)
    }

    grunt.show_alert(__('Import started'), 'info')
  } catch (err) {
    offProgress()
    offChange()
    progressEl.remove()
    grunt.show_alert(__('Error') + ': ' + err.message, 'error')
    if (btn) { btn.disabled = false; btn.textContent = __('Run import') }
  }
}

// ── Reset ─────────────────────────────────────────────────────────────────────

async function _reset(frm) {
  if (!await grunt.confirm(__('Reset the status to "Pending" and run again?'))) return
  await frm.set_value('status', 'Pending')
  await frm.set_value('processed_rows', 0)
  await frm.set_value('error_count', 0)
  await frm.set_value('error_log', null)
  await frm.save()
  document.getElementById('grunt-di-result')?.remove()
}

// ── Result banner ─────────────────────────────────────────────────────────────

function _renderResultBanner(frm, doc) {
  document.getElementById('grunt-di-result')?.remove()

  const status = doc?.status ?? frm.get_value('status')
  if (!status || status === 'Pending' || status === 'In Progress') return

  const processed = doc?.processed_rows ?? frm.get_value('processed_rows') ?? 0
  const total = doc?.total_rows ?? frm.get_value('total_rows') ?? 0
  const errorCount = doc?.error_count ?? frm.get_value('error_count') ?? 0
  const errorLog = _parseErrors(doc?.error_log ?? frm.get_value('error_log'))

  const isOk = status === 'Success'
  const isPartial = status === 'Partial Success'

  const colors = isOk
    ? { bg: '#f0fdf4', border: '#86efac', text: '#166534', badge: '#dcfce7', badgeText: '#166534' }
    : isPartial
      ? { bg: '#fffbeb', border: '#fcd34d', text: '#92400e', badge: '#fef3c7', badgeText: '#92400e' }
      : { bg: '#fef2f2', border: '#fca5a5', text: '#991b1b', badge: '#fee2e2', badgeText: '#991b1b' }

  const icon = isOk ? '✅' : isPartial ? '⚠️' : '❌'
  const title = isOk ? __('Import finished') : isPartial ? __('Partial success') : __('Import error')

  const errorsHtml = errorLog.length
    ? `<details style="margin-top:12px">
        <summary style="cursor:pointer;font-size:12px;font-weight:600;color:${colors.text}">
          ${__('Show {n} errors').replace('{n}', errorLog.length)}
        </summary>
        <ul style="margin-top:8px;padding-left:20px;font-size:12px;font-family:monospace;max-height:200px;overflow-y:auto">
          ${errorLog.map(e => `<li style="margin-bottom:4px"><b>${__('Row {n}:').replace('{n}', e.row)}</b> ${_esc(e.error)}</li>`).join('')}
        </ul>
      </details>`
    : ''

  const banner = document.createElement('div')
  banner.id = 'grunt-di-result'
  banner.style.cssText = `
    margin:16px 0;
    padding:16px 20px;
    border-radius:12px;
    border:1px solid ${colors.border};
    background:${colors.bg};
    color:${colors.text};
    font-size:13px;
  `
  banner.innerHTML = `
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
      <span style="font-size:18px">${icon}</span>
      <span style="font-weight:700;font-size:14px">${title}</span>
      <span style="margin-left:auto;background:${colors.badge};color:${colors.badgeText};
        padding:2px 10px;border-radius:999px;font-size:11px;font-weight:600">
        ${status}
      </span>
    </div>
    <div style="display:flex;gap:20px;font-size:12px">
      <span>${__('Processed:')} <b>${processed}</b> / <b>${total}</b></span>
      ${errorCount ? `<span style="color:#dc2626">${__('Errors:')} <b>${errorCount}</b></span>` : ''}
    </div>
    ${errorsHtml}
  `

  const formEl = document.querySelector('[data-slot="form-renderer"]')
    ?? document.querySelector('.grunt-form-body')
    ?? document.querySelector('main')
  if (formEl) formEl.insertAdjacentElement('afterbegin', banner)
}

function _refreshStatusBanner(frm) {
  document.getElementById('grunt-di-result')?.remove()
  _renderResultBanner(frm)
}

// ── Progress bar ──────────────────────────────────────────────────────────────

function _createProgressBar() {
  document.getElementById('grunt-di-progress')?.remove()
  const el = document.createElement('div')
  el.id = 'grunt-di-progress'
  el.style.cssText = `
    position:fixed;bottom:24px;left:50%;transform:translateX(-50%);
    min-width:320px;padding:14px 20px;border-radius:12px;
    background:var(--color-card,#fff);border:1px solid var(--color-border,#e5e7eb);
    box-shadow:0 8px 24px rgba(0,0,0,0.12);z-index:9999;font-size:13px;
  `
  el.innerHTML = `
    <div style="margin-bottom:8px;font-weight:600">${__('Import in progress...')}</div>
    <div style="background:#e5e7eb;border-radius:999px;height:6px;overflow:hidden">
      <div id="grunt-di-bar" style="background:var(--color-primary,#6366f1);height:100%;width:0%;transition:width .4s"></div>
    </div>
    <div id="grunt-di-label" style="margin-top:6px;color:#6b7280;font-size:11px">0 / —</div>
  `
  document.body.appendChild(el)
  return el
}

function _updateProgressBar(el, pct, processed, total) {
  if (!el.isConnected) return
  const bar = document.getElementById('grunt-di-bar')
  const label = document.getElementById('grunt-di-label')
  if (bar) bar.style.width = pct + '%'
  if (label) label.textContent = `${processed} / ${total} ${__('rows')} (${pct}%)`
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function _authHeaders() {
  const token = localStorage.getItem('grunt_token')
  const h = { 'Content-Type': 'application/json' }
  if (token) h['Authorization'] = 'Bearer ' + token
  return h
}

function _findBtn(label) {
  return [...document.querySelectorAll('button')].find(b => b.textContent.trim() === label) ?? null
}

function _parseErrors(raw) {
  if (!raw) return []
  try { return JSON.parse(typeof raw === 'string' ? raw : JSON.stringify(raw)) } catch { return [] }
}

function _esc(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}
