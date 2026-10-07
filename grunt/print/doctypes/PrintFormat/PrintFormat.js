// PrintFormat — Client Script
// Додає live preview шаблону Jinja2 у правій панелі FormView.

// ── Стан ──────────────────────────────────────────────────────────────────────

let _previewPanel = null   // HTMLDivElement | null
let _previewIframe = null  // HTMLIFrameElement | null
let _debounceTimer = null  // setTimeout id
const DEBOUNCE_MS = 800


// ── Lifecycle hooks ───────────────────────────────────────────────────────────

function on_load(frm) {
  frm.actions.add({
    id: 'preview',
    label: 'Preview',
    icon: 'eye',
    variant: 'secondary',
    visible: (f) => !f.is_new,
    action: (f) => _togglePreview(f),
  })
}

function on_change(frm, fieldname) {
  if (fieldname !== 'template' && fieldname !== 'ref_doctype') return
  if (!_previewPanel || !_previewPanel.isConnected) return

  clearTimeout(_debounceTimer)
  _debounceTimer = setTimeout(() => _refreshPreview(frm), DEBOUNCE_MS)
}

function after_save(frm) {
  // Refresh panel if open after saving
  if (_previewPanel && _previewPanel.isConnected) {
    _refreshPreview(frm)
  }
}


// ── Preview panel ─────────────────────────────────────────────────────────────

function _togglePreview(frm) {
  if (_previewPanel && _previewPanel.isConnected) {
    _destroyPreview()
  } else {
    _createPreview(frm)
    _refreshPreview(frm)
  }
}

function _createPreview(frm) {
  // Find the form content area to split into columns
  const formRoot = document.querySelector('[data-doctype="PrintFormat"]')
    || document.querySelector('.form-content')
    || document.querySelector('main')

  if (!formRoot) return

  // Wrap form in flex container if not already
  const wrapper = formRoot.parentElement
  if (!wrapper) return

  // Panel container
  const panel = document.createElement('div')
  panel.id = 'grunt-print-preview-panel'
  panel.style.cssText = [
    'display:flex',
    'flex-direction:column',
    'width:50%',
    'min-width:320px',
    'max-width:720px',
    'border-left:1px solid var(--color-border, #e5e7eb)',
    'background:var(--color-surface, #fff)',
    'position:fixed',
    'top:0',
    'right:0',
    'bottom:0',
    'z-index:100',
    'box-shadow:-4px 0 16px rgba(0,0,0,0.08)',
  ].join(';')

  // Header
  const header = document.createElement('div')
  header.style.cssText = [
    'display:flex',
    'align-items:center',
    'justify-content:space-between',
    'padding:12px 16px',
    'border-bottom:1px solid var(--color-border, #e5e7eb)',
    'font-weight:600',
    'font-size:14px',
    'flex-shrink:0',
  ].join(';')
  header.innerHTML = `
    <span>${__('Preview')}</span>
    <div style="display:flex;gap:8px;align-items:center">
      <span id="grunt-preview-status" style="font-size:12px;font-weight:400;color:var(--color-muted,#6b7280)"></span>
      <button id="grunt-preview-close"
        style="cursor:pointer;border:none;background:transparent;font-size:18px;line-height:1;padding:0 4px;color:var(--color-muted,#6b7280)"
        title="${__('Close')}">✕</button>
    </div>
  `

  // Toolbar
  const toolbar = document.createElement('div')
  toolbar.style.cssText = [
    'display:flex',
    'gap:8px',
    'padding:8px 16px',
    'border-bottom:1px solid var(--color-border,#e5e7eb)',
    'flex-shrink:0',
  ].join(';')
  toolbar.innerHTML = `
    <button id="grunt-preview-refresh"
      style="cursor:pointer;font-size:12px;padding:4px 10px;border:1px solid var(--color-border,#e5e7eb);border-radius:4px;background:var(--color-bg,#f9fafb)"
      title="${__('Refresh (Ctrl+Enter)')}">↺ ${__('Refresh')}</button>
    <button id="grunt-preview-open"
      style="cursor:pointer;font-size:12px;padding:4px 10px;border:1px solid var(--color-border,#e5e7eb);border-radius:4px;background:var(--color-bg,#f9fafb)"
      title="${__('Open in new tab')}">↗ ${__('New tab')}</button>
  `

  // Iframe
  const iframe = document.createElement('iframe')
  iframe.id = 'grunt-print-preview-iframe'
  iframe.style.cssText = [
    'flex:1',
    'border:none',
    'width:100%',
    'background:#fff',
  ].join(';')
  iframe.setAttribute('sandbox', 'allow-same-origin allow-scripts')

  panel.appendChild(header)
  panel.appendChild(toolbar)
  panel.appendChild(iframe)

  document.body.appendChild(panel)

  _previewPanel = panel
  _previewIframe = iframe

  // Close button
  document.getElementById('grunt-preview-close').addEventListener('click', _destroyPreview)

  // Refresh button
  document.getElementById('grunt-preview-refresh').addEventListener('click', () => _refreshPreview(frm))

  // Open in new tab
  document.getElementById('grunt-preview-open').addEventListener('click', () => _openInNewTab(frm))

  // Keyboard shortcut: Ctrl+Enter to refresh
  document.addEventListener('keydown', _handleKeydown = (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault()
      _refreshPreview(frm)
    }
    if (e.key === 'Escape') {
      _destroyPreview()
    }
  })
}

let _handleKeydown = null

function _destroyPreview() {
  if (_previewPanel) {
    _previewPanel.remove()
    _previewPanel = null
    _previewIframe = null
  }
  if (_handleKeydown) {
    document.removeEventListener('keydown', _handleKeydown)
    _handleKeydown = null
  }
  clearTimeout(_debounceTimer)
}


// ── API call ──────────────────────────────────────────────────────────────────

async function _refreshPreview(frm) {
  const doctype = frm.get_value('ref_doctype')
  const template = frm.get_value('template')

  if (!doctype || !template) {
    _setIframeContent('<p style="padding:2rem;color:#6b7280">' + __('Specify a document type and a template to preview.') + '</p>')
    return
  }

  _setStatus(__('Updating...'))

  const token = localStorage.getItem('grunt_token')
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = 'Bearer ' + token

  try {
    const resp = await fetch(`/api/v1/docs/${encodeURIComponent(doctype)}/print-preview`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ template }),
    })

    if (!resp.ok) {
      const text = await resp.text()
      _setIframeContent(`<pre style="padding:1rem;color:red;white-space:pre-wrap">HTTP ${resp.status}:\n${text}</pre>`)
      _setStatus(__('Error') + ' ' + resp.status)
      return
    }

    const html = await resp.text()
    _setIframeContent(html)
    _setStatus(__('Updated'))

    setTimeout(() => _setStatus(''), 2000)
  } catch (err) {
    _setIframeContent(`<pre style="padding:1rem;color:red;white-space:pre-wrap">${__('Network error:')}\n${err.message}</pre>`)
    _setStatus(__('Error'))
  }
}

async function _openInNewTab(frm) {
  const doctype = frm.get_value('ref_doctype')
  const template = frm.get_value('template')
  if (!doctype || !template) return

  const token = localStorage.getItem('grunt_token')
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = 'Bearer ' + token

  try {
    const resp = await fetch(`/api/v1/docs/${encodeURIComponent(doctype)}/print-preview`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ template }),
    })
    if (!resp.ok) return
    const html = await resp.text()
    const blob = new Blob([html], { type: 'text/html' })
    const url = URL.createObjectURL(blob)
    const win = window.open(url, '_blank')
    if (win) setTimeout(() => URL.revokeObjectURL(url), 5000)
  } catch { /* ignore */ }
}


// ── Helpers ───────────────────────────────────────────────────────────────────

function _setIframeContent(html) {
  if (!_previewIframe) return
  const doc = _previewIframe.contentDocument || _previewIframe.contentWindow?.document
  if (!doc) return
  doc.open()
  doc.write(html)
  doc.close()
}

function _setStatus(msg) {
  const el = document.getElementById('grunt-preview-status')
  if (el) el.textContent = msg
}
