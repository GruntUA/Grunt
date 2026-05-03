// OutgoingWebhook — Client Script
// Додає кнопку "Тест" та панель останніх доставок на форму вебхуку.

// ── Стан ──────────────────────────────────────────────────────────────────────
let _logsPanel = null

// ── Lifecycle hooks ───────────────────────────────────────────────────────────

function on_load(frm) {
  if (frm.is_new) return

  frm.add_button('Тест', () => _runTest(frm), { variant: 'secondary' })
  frm.add_button('Журнал доставок', () => _toggleLogs(frm), { variant: 'ghost' })
}

function after_save(frm) {
  frm.add_button('Тест', () => _runTest(frm), { variant: 'secondary' })
  frm.add_button('Журнал доставок', () => _toggleLogs(frm), { variant: 'ghost' })
}


// ── Тестова доставка ──────────────────────────────────────────────────────────

async function _runTest(frm) {
  const id = frm.doc_id || frm.get_value('id') || frm.get_value('name')
  if (!id) { alert('Збережіть вебхук перед тестуванням.'); return }

  const btn = document.querySelector('[data-grunt-btn="Тест"]')
    || [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Тест')
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Надсилання...' }

  const token = localStorage.getItem('grunt_token')
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = 'Bearer ' + token

  try {
    const resp = await fetch(`/api/v1/webhooks/outgoing/${encodeURIComponent(id)}/test`, {
      method: 'POST',
      headers,
    })
    const json = await resp.json()
    const log = json?.data ?? {}
    _showTestResult(log)
    // Refresh logs panel if open
    if (_logsPanel && _logsPanel.isConnected) _loadLogs(frm)
  } catch (err) {
    _showTestResult({ success: false, error: err.message })
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Тест' }
  }
}

function _showTestResult(log) {
  // Remove previous result
  document.getElementById('grunt-webhook-test-result')?.remove()

  const ok = log.success
  const div = document.createElement('div')
  div.id = 'grunt-webhook-test-result'
  div.style.cssText = [
    'position:fixed',
    'bottom:24px',
    'right:24px',
    'min-width:320px',
    'max-width:480px',
    'padding:14px 18px',
    'border-radius:10px',
    'box-shadow:0 8px 24px rgba(0,0,0,0.15)',
    'z-index:9999',
    'font-size:13px',
    'line-height:1.5',
    ok
      ? 'background:#f0fdf4;border:1px solid #86efac;color:#166534'
      : 'background:#fef2f2;border:1px solid #fca5a5;color:#991b1b',
  ].join(';')

  let html = `<div style="font-weight:600;margin-bottom:6px">${ok ? '✅ Успішно' : '❌ Помилка'}</div>`
  if (log.status_code) html += `<div>HTTP ${log.status_code} · ${log.duration_ms ?? 0} мс</div>`
  if (log.error) html += `<div style="margin-top:4px;font-family:monospace;font-size:12px">${_esc(log.error)}</div>`
  if (log.response_body) {
    html += `<details style="margin-top:8px"><summary style="cursor:pointer;font-size:12px">Відповідь</summary>
      <pre style="margin-top:4px;overflow:auto;max-height:120px;font-size:11px;white-space:pre-wrap">${_esc(log.response_body.slice(0, 800))}</pre></details>`
  }
  html += `<button onclick="this.parentElement.remove()" style="position:absolute;top:10px;right:12px;background:none;border:none;cursor:pointer;font-size:16px;opacity:.6">✕</button>`
  div.innerHTML = html
  div.style.position = 'relative'
  document.body.appendChild(div)
  setTimeout(() => div.remove(), 12000)
}


// ── Панель журналу ────────────────────────────────────────────────────────────

function _toggleLogs(frm) {
  if (_logsPanel && _logsPanel.isConnected) {
    _logsPanel.remove()
    _logsPanel = null
    return
  }
  _createLogsPanel(frm)
  _loadLogs(frm)
}

function _createLogsPanel(frm) {
  const panel = document.createElement('div')
  panel.id = 'grunt-webhook-logs-panel'
  panel.style.cssText = [
    'position:fixed',
    'top:0',
    'right:0',
    'bottom:0',
    'width:480px',
    'display:flex',
    'flex-direction:column',
    'background:var(--color-card,#fff)',
    'border-left:1px solid var(--color-border,#e5e7eb)',
    'box-shadow:-4px 0 16px rgba(0,0,0,0.08)',
    'z-index:200',
  ].join(';')

  panel.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:space-between;padding:14px 18px;border-bottom:1px solid var(--color-border,#e5e7eb);flex-shrink:0">
      <span style="font-weight:600;font-size:14px">Журнал доставок</span>
      <div style="display:flex;gap:8px;align-items:center">
        <button id="gwl-refresh" title="Оновити"
          style="font-size:12px;padding:4px 10px;border:1px solid var(--color-border,#e5e7eb);border-radius:6px;cursor:pointer;background:transparent">↺</button>
        <button id="gwl-close"
          style="background:none;border:none;cursor:pointer;font-size:18px;opacity:.5;line-height:1">✕</button>
      </div>
    </div>
    <div id="gwl-body" style="flex:1;overflow-y:auto;padding:12px"></div>
  `

  document.body.appendChild(panel)
  _logsPanel = panel

  document.getElementById('gwl-close').addEventListener('click', () => { panel.remove(); _logsPanel = null })
  document.getElementById('gwl-refresh').addEventListener('click', () => _loadLogs(frm))
}

async function _loadLogs(frm) {
  const id = frm.doc_id || frm.get_value('id') || frm.get_value('name')
  const body = document.getElementById('gwl-body')
  if (!body) return

  body.innerHTML = '<div style="padding:20px;text-align:center;color:#9ca3af;font-size:13px">Завантаження...</div>'

  const token = localStorage.getItem('grunt_token')
  const headers = token ? { 'Authorization': 'Bearer ' + token } : {}

  try {
    const url = `/api/v1/docs/WebhookLog?filter[webhook]=${encodeURIComponent(id)}&sort_by=created_at&sort_order=desc&per_page=30`
    const resp = await fetch(url, { headers })
    const json = await resp.json()
    const logs = json?.data?.items ?? json?.data ?? []

    if (!logs.length) {
      body.innerHTML = '<div style="padding:20px;text-align:center;color:#9ca3af;font-size:13px">Доставок ще немає</div>'
      return
    }

    body.innerHTML = logs.map(log => {
      const ok = log.success || log.success === 1
      const time = log.created_at ? new Date(log.created_at).toLocaleString('uk-UA', {day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}) : '—'
      const badge = ok
        ? '<span style="background:#dcfce7;color:#166534;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600">✓ OK</span>'
        : '<span style="background:#fee2e2;color:#991b1b;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600">✕ Error</span>'
      const testBadge = (log.is_test || log.is_test === 1) ? '<span style="background:#e0f2fe;color:#0369a1;padding:2px 6px;border-radius:999px;font-size:10px;margin-left:4px">test</span>' : ''
      return `
        <div style="border:1px solid var(--color-border,#e5e7eb);border-radius:8px;margin-bottom:8px;overflow:hidden">
          <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 14px;background:var(--color-muted,#f9fafb)">
            <div style="display:flex;align-items:center;gap:8px">
              ${badge}${testBadge}
              <span style="font-size:12px;color:#6b7280">${log.event || '—'}</span>
            </div>
            <span style="font-size:11px;color:#9ca3af">${time}</span>
          </div>
          <div style="padding:10px 14px;font-size:12px">
            <div style="color:#6b7280;margin-bottom:4px;font-family:monospace;font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${_esc(log.url || '')}">
              ${_esc((log.url || '').slice(0, 60))}${(log.url || '').length > 60 ? '…' : ''}
            </div>
            <div style="display:flex;gap:12px;color:#374151">
              ${log.status_code ? `<span>HTTP ${log.status_code}</span>` : ''}
              ${log.duration_ms != null ? `<span>${log.duration_ms} мс</span>` : ''}
              ${log.error ? `<span style="color:#dc2626" title="${_esc(log.error)}">⚠ ${_esc(log.error.slice(0, 40))}</span>` : ''}
            </div>
          </div>
        </div>
      `
    }).join('')
  } catch (err) {
    body.innerHTML = `<div style="padding:20px;color:#dc2626;font-size:13px">Помилка: ${_esc(err.message)}</div>`
  }
}


// ── Helpers ───────────────────────────────────────────────────────────────────

function _esc(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}
