<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick, createApp, h } from 'vue'
import { useRouter } from 'vue-router'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import 'leaflet.browser.print/dist/leaflet.browser.print.js'
import { MapPin, RefreshCw, Loader2 } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { docsApi } from '@/core/api/docs'
import type { DocType, DocTypeMapView, ScriptMenuItem, ActiveFilter } from '@/types'
import type { Component } from 'vue'

// ── Props ────────────────────────────────────────────────────────────────────
const props = defineProps<{
  doctype: DocType
  geoField: string
  workspace?: string
  search?: string
  filters?: ActiveFilter[]
}>()

const emit = defineEmits<{
  'register-menu-items': [items: ScriptMenuItem[]]
  'unregister-menu-items': [items: ScriptMenuItem[]]
}>()

// ── Map config (from doctype.map_view or defaults) ───────────────────────────
const cfg = computed<DocTypeMapView>(() => props.doctype.map_view ?? {})
const labelField = computed(() => cfg.value.label_field ?? props.doctype.title_field ?? 'name')
const colorField = computed(() => cfg.value.color_field ?? null)
const colorMap = computed(() => cfg.value.color_map ?? {})
const defaultColor = computed(() => cfg.value.default_color ?? 'var(--color-primary, #3b82f6)')

// Auto-derive iconField: "object_type__color" → "object_type__icon", or explicit cfg
const iconField = computed(() => {
  if (cfg.value.icon_field) return cfg.value.icon_field
  if (colorField.value?.endsWith('__color')) return colorField.value.replace('__color', '__icon')
  return null
})

// ── Popup fields (user-configured columns or in_list_view fallback) ───────────
const POPUP_SKIP_TYPES = new Set([
  'Section', 'Column', 'Tab', 'Table', 'MultiLink',
  'LongText', 'RichText', 'Code', 'Geolocation', 'Attach', 'Image', 'Signature', 'JSON',
])

const popupFields = computed(() => {
  const storageKey = `grunt_columns_v2_${props.doctype.name}`
  const saved = localStorage.getItem(storageKey)
  const savedKeys: string[] | null = saved ? (JSON.parse(saved) as string[]) : null

  const allFields = props.doctype.fields.filter(
    f => !POPUP_SKIP_TYPES.has(f.fieldtype) && !f.hidden && f.fieldname !== props.geoField
  )

  if (savedKeys?.length) {
    // Respect user's column order/selection
    return savedKeys
      .map(key => allFields.find(f => f.fieldname === key))
      .filter((f): f is NonNullable<typeof f> => f !== undefined)
  }
  // Fallback: in_list_view fields
  const listFields = allFields.filter(f => f.in_list_view)
  return listFields.length ? listFields : allFields.slice(0, 5)
})

function formatPopupValue(value: unknown, fieldtype: string): string {
  if (value === null || value === undefined || value === '') return '—'
  if (fieldtype === 'Check') return value ? '✓' : '✗'
  if (fieldtype === 'Rating') {
    const n = Number(value)
    if (isNaN(n)) return '—'
    const full = Math.floor(n)
    const half = n - full >= 0.5
    const empty = 5 - full - (half ? 1 : 0)
    return '★'.repeat(full) + (half ? '½' : '') + '☆'.repeat(empty) + ` ${n}`
  }
  if (fieldtype === 'Float' && typeof value === 'number') return value.toFixed(2).replace(/\.?0+$/, '')
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

// ── State ────────────────────────────────────────────────────────────────────
const router = useRouter()
const mapEl = ref<HTMLDivElement | null>(null)
const isLoading = ref(false)
const markerCount = ref(0)
const skippedCount = ref(0)

// Coordinate jump
const coordInput = ref('')
const coordError = ref(false)
let coordMarker: L.Marker | null = null

let map: L.Map | null = null
let markerLayer: L.LayerGroup | null = null
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let browserPrint: any = null

// ── Marker helpers ────────────────────────────────────────────────────────────
function resolveColor(row: Record<string, unknown>): string {
  if (colorField.value) {
    const val = String(row[colorField.value] ?? '')
    if (val) {
      // Direct color value (e.g. from object_type__color injected by _resolve_link_labels)
      if (val.startsWith('#') || val.startsWith('rgb') || val.startsWith('hsl')) return val
      // Mapped color (legacy color_map approach)
      if (colorMap.value[val]) return colorMap.value[val]
    }
  }
  // Support CSS vars — resolve at runtime against the :root element
  const raw = defaultColor.value
  if (raw.startsWith('var(')) {
    const varName = raw.match(/var\(([^,)]+)/)?.[1]?.trim()
    if (varName) {
      const resolved = getComputedStyle(document.documentElement).getPropertyValue(varName).trim()
      return resolved || '#3b82f6'
    }
  }
  return raw
}

// ── Lucide SVG path cache ─────────────────────────────────────────────────────
// Maps kebab icon name → inner SVG paths string (rendered once, reused forever)
const _iconPathCache = new Map<string, string>()
type IconMap = Record<string, Component>
let _lucideLib: IconMap | null = null

async function ensureLucide(): Promise<IconMap> {
  if (!_lucideLib) _lucideLib = await import('lucide-vue-next') as unknown as IconMap
  return _lucideLib
}

async function getIconPaths(iconName: string): Promise<string> {
  if (_iconPathCache.has(iconName)) return _iconPathCache.get(iconName)!
  const lib = await ensureLucide()
  const pascal = iconName.split('-').map(s => s.charAt(0).toUpperCase() + s.slice(1)).join('')
  const IconComp = lib[pascal] as Component | undefined
  if (!IconComp) return ''
  // Render into a detached div to extract SVG children
  const div = document.createElement('div')
  const app = createApp({ render: () => h(IconComp, { size: 12, 'stroke-width': 2.5 }) })
  app.mount(div)
  const paths = div.querySelector('svg')?.innerHTML ?? ''
  app.unmount()
  _iconPathCache.set(iconName, paths)
  return paths
}

function createIcon(color: string, iconPaths?: string): L.DivIcon {
  const inner = iconPaths
    // Icon SVG centered in the white circle area (viewBox 0 0 24 32, circle at 12,12 r=6)
    ? `<circle cx="12" cy="12" r="7" fill="white" opacity="0.92"/>
       <svg x="6" y="6" width="12" height="12" viewBox="0 0 24 24"
         fill="none" stroke="${color}" stroke-width="2.5"
         stroke-linecap="round" stroke-linejoin="round">${iconPaths}</svg>`
    : `<circle cx="12" cy="12" r="5" fill="white" opacity="0.85"/>`

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 32" width="24" height="32">
    <path d="M12 0C5.373 0 0 5.373 0 12c0 9 12 20 12 20s12-11 12-20C24 5.373 18.627 0 12 0z"
      fill="${color}" stroke="white" stroke-width="1.5"/>
    ${inner}
  </svg>`
  return L.divIcon({
    html: svg,
    className: '',
    iconSize: [24, 32],
    iconAnchor: [12, 32],
    popupAnchor: [0, -34],
  })
}

// ── Data loading ──────────────────────────────────────────────────────────────
// Store raw rows for export
const loadedRows = ref<Array<{ row: Record<string, unknown>; lat: number; lng: number }>>([])

async function loadMarkers() {
  if (!map) return
  isLoading.value = true
  markerLayer?.clearLayers()
  loadedRows.value = []

  try {
    const fields = new Set([props.geoField, labelField.value, 'name', 'id'])
    if (colorField.value) {
      // "object_type__color" → request base field "object_type"; backend injects __color
      const baseField = colorField.value.includes('__') ? colorField.value.split('__')[0] : colorField.value
      fields.add(baseField)
    }
    popupFields.value.forEach(f => fields.add(f.fieldname))

    const result = await docsApi.list(props.doctype.name, {
      page: 1,
      per_page: 5000,
      fields: [...fields].join(','),
      search: props.search || undefined,
      filters: props.filters?.length ? props.filters : undefined,
    })

    // Pre-render all unique icon paths before building markers
    const rows = result.data as Record<string, unknown>[]
    if (iconField.value) {
      const uniqueIcons = [...new Set(rows.map(r => String(r[iconField.value!] ?? '')).filter(Boolean))]
      await Promise.all(uniqueIcons.map(name => getIconPaths(name)))
    }

    const bounds: L.LatLngTuple[] = []
    let skipped = 0

    for (const row of rows) {
      const geo = row[props.geoField]
      if (!geo || typeof geo !== 'object') { skipped++; continue }
      const { lat, lng } = geo as Record<string, unknown>
      if (lat == null || lng == null) { skipped++; continue }
      const latN = Number(lat)
      const lngN = Number(lng)
      if (isNaN(latN) || isNaN(lngN)) { skipped++; continue }

      loadedRows.value.push({ row, lat: latN, lng: lngN })
      const color = resolveColor(row)
      const iconName = iconField.value ? String(row[iconField.value] ?? '') : ''
      const iconPaths = iconName ? (_iconPathCache.get(iconName) ?? '') : ''
      const icon = createIcon(color, iconPaths || undefined)
      const label = String(row[labelField.value] ?? row['name'] ?? '')

      // Build popup field rows (skip label field — already shown as title)
      const fieldRows = popupFields.value
        .filter(f => f.fieldname !== labelField.value)
        .map(f => {
          const val = formatPopupValue(row[f.fieldname], f.fieldtype)
          return `<tr>
            <td class="popup-field-label">${f.label}</td>
            <td class="popup-field-value">${val}</td>
          </tr>`
        })
        .join('')

      const tableHtml = fieldRows
        ? `<table class="popup-fields">${fieldRows}</table>`
        : ''

      const marker = L.marker([latN, lngN], { icon })
      marker.bindPopup(
        `<div class="popup-title">${label}</div>
         ${tableHtml}
         <div class="popup-coords">${latN.toFixed(6)}, ${lngN.toFixed(6)}</div>
         <a href="#" data-id="${String(row['id'] ?? row['name'])}"
            class="popup-open-link open-doc">
           Відкрити →
         </a>`,
        { maxWidth: 280 }
      )
      marker.on('popupopen', () => {
        const el = marker.getPopup()?.getElement()
        el?.querySelector('.open-doc')?.addEventListener('click', (e) => {
          e.preventDefault()
          const id = (e.currentTarget as HTMLElement).dataset.id
          if (id) navigateToDoc(id)
        })
      })

      markerLayer?.addLayer(marker)
      bounds.push([latN, lngN])
    }

    markerCount.value = loadedRows.value.length
    skippedCount.value = skipped

    if (bounds.length === 1) {
      map.setView(bounds[0], 14)
    } else if (bounds.length > 1) {
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 16 })
    }
  } finally {
    isLoading.value = false
  }
}

function navigateToDoc(id: string) {
  const ws = props.workspace ?? 'grunt'
  router.push(`/${ws}/list/${props.doctype.name}/${id}`)
}

// ── Coordinate jump ───────────────────────────────────────────────────────────
function gotoCoord() {
  coordError.value = false
  const raw = coordInput.value.trim()
  if (!raw) return

  // Accept "lat,lng" or "lat, lng" or "lat lng" or "lat;lng"
  const parts = raw.split(/[\s,;]+/).map(s => s.trim()).filter(Boolean)
  if (parts.length < 2) { coordError.value = true; return }
  const lat = parseFloat(parts[0])
  const lng = parseFloat(parts[1])
  if (isNaN(lat) || isNaN(lng) || lat < -90 || lat > 90 || lng < -180 || lng > 180) {
    coordError.value = true
    return
  }

  if (!map) return

  // Remove previous coord marker
  if (coordMarker) { coordMarker.remove(); coordMarker = null }

  const crosshairSvg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 40" width="32" height="40">
    <path d="M16 0C8.268 0 2 6.268 2 14c0 10.5 14 26 14 26S30 24.5 30 14C30 6.268 23.732 0 16 0z"
      fill="#ef4444" stroke="white" stroke-width="1.5"/>
    <circle cx="16" cy="14" r="5" fill="white" opacity="0.9"/>
    <line x1="16" y1="6" x2="16" y2="22" stroke="#ef4444" stroke-width="2" stroke-linecap="round"/>
    <line x1="8" y1="14" x2="24" y2="14" stroke="#ef4444" stroke-width="2" stroke-linecap="round"/>
  </svg>`

  const icon = L.divIcon({
    html: crosshairSvg,
    className: '',
    iconSize: [32, 40],
    iconAnchor: [16, 40],
    popupAnchor: [0, -42],
  })

  coordMarker = L.marker([lat, lng], { icon })
    .addTo(map)
    .bindPopup(`<div class="popup-title">📍 Позначена точка</div>
      <div class="popup-coords">${lat.toFixed(6)}, ${lng.toFixed(6)}</div>`)
    .openPopup()

  map.flyTo([lat, lng], 15, { duration: 1.2 })
}

function clearCoordMarker() {
  if (coordMarker) { coordMarker.remove(); coordMarker = null }
  coordInput.value = ''
  coordError.value = false
}

// ── Export ────────────────────────────────────────────────────────────────────
function exportGeoJSON() {
  const features = loadedRows.value.map(({ row, lat, lng }) => ({
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [lng, lat] },
    properties: Object.fromEntries(
      Object.entries(row).filter(([k]) => k !== props.geoField)
    ),
  }))
  downloadBlob(
    JSON.stringify({ type: 'FeatureCollection', features }, null, 2),
    `${props.doctype.name}_map.geojson`,
    'application/geo+json'
  )
}

function exportCSV() {
  const fields = new Set([labelField.value, 'name'])
  if (colorField.value) fields.add(colorField.value)
  const headers = ['lat', 'lng', ...fields]
  const lines = [
    headers.join(','),
    ...loadedRows.value.map(({ row, lat, lng }) =>
      [lat, lng, ...[...fields].map(f => csvEscape(String(row[f] ?? '')))].join(',')
    ),
  ]
  downloadBlob(lines.join('\n'), `${props.doctype.name}_map.csv`, 'text/csv')
}

// ── Print area selector ───────────────────────────────────────────────────────

const isPrintMode = ref(false)
type PrintFormat = 'a4p' | 'a4l' | 'a3p' | 'a3l'
const printFormat = ref<PrintFormat>('a4p')
const mapWrapEl = ref<HTMLDivElement | null>(null)

const PRINT_FORMATS: Record<PrintFormat, { label: string; ratio: number }> = {
  a4p: { label: 'A4 книжна',   ratio: 210 / 297 },
  a4l: { label: 'A4 альбомна', ratio: 297 / 210 },
  a3p: { label: 'A3 книжна',   ratio: 297 / 420 },
  a3l: { label: 'A3 альбомна', ratio: 420 / 297 },
}

// Rectangle position/size in container pixels
const printRect = ref({ x: 0, y: 0, w: 300, h: 424 })

function initPrintRect() {
  const el = mapWrapEl.value
  if (!el) return
  const cw = el.clientWidth, ch = el.clientHeight
  const ratio = PRINT_FORMATS[printFormat.value].ratio
  let w = cw * 0.65, h = w / ratio
  if (h > ch * 0.82) { h = ch * 0.82; w = h * ratio }
  printRect.value = { x: (cw - w) / 2, y: (ch - h) / 2, w, h }
}

watch(printFormat, () => {
  if (!isPrintMode.value || !mapWrapEl.value) return
  const ratio = PRINT_FORMATS[printFormat.value].ratio
  const r = printRect.value
  const cx = r.x + r.w / 2, cy = r.y + r.h / 2
  let w = r.w, h = w / ratio
  const el = mapWrapEl.value
  if (h > el.clientHeight * 0.95) { h = el.clientHeight * 0.95; w = h * ratio }
  printRect.value = { x: cx - w / 2, y: cy - h / 2, w, h }
})

function enterPrintMode() {
  isPrintMode.value = true
  nextTick(initPrintRect)
}

function cancelPrint() {
  isPrintMode.value = false
}

// Maps our format keys to leaflet.browser.print mode params
const PRINT_MODE_MAP: Record<PrintFormat, { pageSize: string; orientation: 'Portrait' | 'Landscape' }> = {
  a4p: { pageSize: 'A4', orientation: 'Portrait'  },
  a4l: { pageSize: 'A4', orientation: 'Landscape' },
  a3p: { pageSize: 'A3', orientation: 'Portrait'  },
  a3l: { pageSize: 'A3', orientation: 'Landscape' },
}

function confirmPrint() {
  if (!map || !browserPrint) return
  const r = printRect.value
  const tl = map.containerPointToLatLng(L.point(r.x, r.y))
  const br = map.containerPointToLatLng(L.point(r.x + r.w, r.y + r.h))
  const bounds = L.latLngBounds(tl, br)

  isPrintMode.value = false

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const LX = L as any

  // Disable zoom snapping on the overlay map so fitBounds uses fractional zoom
  // and prints exactly the selected area (default zoomSnap:1 rounds down → shows more)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const onPrintStart = (e: any) => {
    e.printMap.options.zoomSnap = 0
    map!.off(LX.BrowserPrint.Event.PrintStart, onPrintStart)
  }
  map.on(LX.BrowserPrint.Event.PrintStart, onPrintStart)

  const { pageSize, orientation } = PRINT_MODE_MAP[printFormat.value]
  const mode = new LX.BrowserPrint.Mode(orientation, {
    pageSize,
    invalidateBounds: true,
  })

  // Set isPrinting flag that the plugin's tile-polling interval relies on
  ;(map as any).isPrinting = true
  browserPrint.cancelNextPrinting = false
  browserPrint._print(mode, bounds)
}

// ── Drag to move ─────────────────────────────────────────────────────────────

let _drag: { sx: number; sy: number; ox: number; oy: number } | null = null

function startMove(e: MouseEvent) {
  _drag = { sx: e.clientX, sy: e.clientY, ox: printRect.value.x, oy: printRect.value.y }
  window.addEventListener('mousemove', onDragMove)
  window.addEventListener('mouseup', stopDrag, { once: true })
  e.preventDefault()
}

function onDragMove(e: MouseEvent) {
  if (!_drag || !mapWrapEl.value) return
  const el = mapWrapEl.value
  const x = Math.max(0, Math.min(_drag.ox + e.clientX - _drag.sx, el.clientWidth  - printRect.value.w))
  const y = Math.max(0, Math.min(_drag.oy + e.clientY - _drag.sy, el.clientHeight - printRect.value.h))
  printRect.value = { ...printRect.value, x, y }
}

function stopDrag() {
  _drag = null
  window.removeEventListener('mousemove', onDragMove)
}

// ── Resize handles ────────────────────────────────────────────────────────────

type Handle = 'nw' | 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w'
let _rsz: { handle: Handle; sx: number; sy: number; r0: typeof printRect.value } | null = null

function startResize(handle: Handle, e: MouseEvent) {
  _rsz = { handle, sx: e.clientX, sy: e.clientY, r0: { ...printRect.value } }
  window.addEventListener('mousemove', onResizeMove)
  window.addEventListener('mouseup', stopResize, { once: true })
  e.preventDefault()
  e.stopPropagation()
}

const MIN_SIZE = 80

function onResizeMove(e: MouseEvent) {
  if (!_rsz || !mapWrapEl.value) return
  const { handle, sx, sy, r0 } = _rsz
  const el = mapWrapEl.value
  const ratio = PRINT_FORMATS[printFormat.value].ratio
  const dx = e.clientX - sx, dy = e.clientY - sy

  let x = r0.x, y = r0.y, w = r0.w, h = r0.h

  // Horizontal-led handles
  if (handle === 'e' || handle === 'ne' || handle === 'se') {
    w = Math.max(MIN_SIZE, r0.w + dx); h = w / ratio
  } else if (handle === 'w' || handle === 'nw' || handle === 'sw') {
    w = Math.max(MIN_SIZE, r0.w - dx); h = w / ratio; x = r0.x + r0.w - w
  // Vertical-led handles
  } else if (handle === 's') {
    h = Math.max(MIN_SIZE, r0.h + dy); w = h * ratio
  } else if (handle === 'n') {
    h = Math.max(MIN_SIZE, r0.h - dy); w = h * ratio; y = r0.y + r0.h - h
  }

  // Anchor y for horizontal handles
  if (handle === 'e' || handle === 'w')  y = r0.y + r0.h / 2 - h / 2
  if (handle === 'ne' || handle === 'e') y = r0.y + r0.h - h
  // Anchor x for vertical handles
  if (handle === 'n' || handle === 's')  x = r0.x + r0.w / 2 - w / 2

  // Clamp to container
  x = Math.max(0, Math.min(x, el.clientWidth  - w))
  y = Math.max(0, Math.min(y, el.clientHeight - h))

  printRect.value = { x, y, w, h }
}

function stopResize() {
  _rsz = null
  window.removeEventListener('mousemove', onResizeMove)
}

function exportPrint() {
  enterPrintMode()
}

function csvEscape(v: string) {
  return v.includes(',') || v.includes('"') || v.includes('\n') ? `"${v.replace(/"/g, '""')}"` : v
}

function downloadBlob(content: string, filename: string, mime: string) {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────
const menuItems: ScriptMenuItem[] = [
  { label: 'Експорт GeoJSON', action: exportGeoJSON, separator_before: true },
  { label: 'Експорт CSV', action: exportCSV },
  { label: 'Друк / PDF', action: exportPrint },
]

onMounted(() => {
  if (!mapEl.value) return
  map = L.map(mapEl.value, {
    center: [49.0, 32.0],
    zoom: 6,
    zoomControl: true,
  })
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a>',
    maxZoom: 19,
  }).addTo(map)
  markerLayer = L.layerGroup().addTo(map)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  browserPrint = (L as any).browserPrint(map, { documentTitle: '' })
  loadMarkers()
  emit('register-menu-items', menuItems)
})

onUnmounted(() => {
  emit('unregister-menu-items', menuItems)
  map?.remove()
  map = null
  markerLayer = null
  browserPrint = null
})

watch(() => props.geoField, loadMarkers)
watch(() => props.search, loadMarkers)
watch(() => props.filters, loadMarkers, { deep: true })
</script>

<template>
  <div class="flex flex-col h-[calc(100vh-14rem)] rounded-xl overflow-hidden shadow-md ring-1 ring-border/60">
    <!-- Toolbar -->
    <div class="flex items-center justify-between px-4 py-2 bg-card border-b border-border/60 shrink-0 gap-3">
      <div class="flex items-center gap-2 text-sm text-muted-foreground shrink-0">
        <MapPin class="size-4 text-primary" />
        <span v-if="isLoading" class="flex items-center gap-1.5">
          <Loader2 class="size-3.5 animate-spin" /> Завантаження...
        </span>
        <span v-else>
          <span class="font-medium text-foreground">{{ markerCount }}</span> мітк{{ markerCount === 1 ? 'а' : markerCount < 5 ? 'и' : '' }}
          <span v-if="skippedCount" class="ml-2 text-xs text-muted-foreground/60">
            ({{ skippedCount }} без координат)
          </span>
        </span>
      </div>

      <!-- Coordinate jump input -->
      <div class="flex items-center gap-1.5 flex-1 max-w-xs relative">
        <input
          v-model="coordInput"
          placeholder="46.844167, 35.402538"
          class="h-8 w-full rounded-md border px-2.5 py-1 text-xs bg-background placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 transition-colors"
          :class="coordError
            ? 'border-destructive focus:ring-destructive/40 text-destructive'
            : 'border-input focus:ring-primary/30'"
          @keydown.enter="gotoCoord"
          @input="coordError = false"
        />
        <button
          v-if="coordInput"
          type="button"
          class="absolute right-1 top-1/2 -translate-y-1/2 text-muted-foreground/50 hover:text-foreground transition-colors p-0.5"
          @click="clearCoordMarker"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="size-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>

      <Button variant="ghost" size="sm" class="h-8 w-8 p-0 shrink-0" :disabled="isLoading" @click="loadMarkers">
        <RefreshCw class="size-3.5" :class="{ 'animate-spin': isLoading }" />
      </Button>
    </div>

    <!-- Map container + print overlay wrapper -->
    <div ref="mapWrapEl" class="flex-1 w-full relative">
      <div ref="mapEl" class="absolute inset-0" />

      <!-- ── Print area selector ── -->
      <template v-if="isPrintMode">
        <!-- Dark overlay with "hole" via box-shadow on the rect -->
        <div class="absolute inset-0 z-[2000] select-none" @mousedown.self.prevent>

          <!-- Format selector bar -->
          <div class="absolute top-3 left-1/2 -translate-x-1/2 z-10
                      flex items-center gap-2 px-3 py-1.5
                      bg-black/80 text-white text-xs rounded-full shadow-xl backdrop-blur-sm">
            <span class="text-white/60 mr-1">Формат:</span>
            <button v-for="(fmt, key) in PRINT_FORMATS" :key="key"
                    class="px-2 py-0.5 rounded transition-colors"
                    :class="printFormat === key
                      ? 'bg-white text-black font-semibold'
                      : 'hover:bg-white/20'"
                    @click="printFormat = key">
              {{ fmt.label }}
            </button>
            <span class="mx-1 text-white/30">|</span>
            <button class="px-2 py-0.5 rounded bg-primary text-primary-foreground font-semibold hover:bg-primary/80 transition-colors"
                    @click="confirmPrint">
              Надрукувати
            </button>
            <button class="px-2 py-0.5 rounded hover:bg-white/20 transition-colors"
                    @click="cancelPrint">
              Скасувати
            </button>
          </div>

          <!-- Selection rectangle -->
          <div class="print-rect-box absolute cursor-move border-2 border-white"
               :style="{
                 left:   printRect.x + 'px',
                 top:    printRect.y + 'px',
                 width:  printRect.w + 'px',
                 height: printRect.h + 'px',
               }"
               @mousedown.stop="startMove">

            <!-- Size label -->
            <div class="absolute -bottom-6 left-1/2 -translate-x-1/2
                        text-white text-[11px] whitespace-nowrap bg-black/60 px-1.5 py-0.5 rounded">
              {{ Math.round(printRect.w) }} × {{ Math.round(printRect.h) }} px
            </div>

            <!-- 8 resize handles -->
            <div v-for="h in (['nw','n','ne','e','se','s','sw','w'] as const)" :key="h"
                 class="print-handle"
                 :class="`handle-${h}`"
                 @mousedown.stop="startResize(h, $event)" />
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style>
/* Override Leaflet popup styles to match app design */
.leaflet-popup-content-wrapper {
  border-radius: 0.5rem;
  box-shadow: 0 4px 16px rgba(0,0,0,0.12);
  font-family: inherit;
  font-size: 0.875rem;
}
.leaflet-popup-content {
  margin: 10px 14px;
  line-height: 1.5;
}
.leaflet-popup-tip {
  background: white;
}

/* Popup content styles */
.popup-title {
  font-weight: 600;
  font-size: 0.875rem;
  margin-bottom: 6px;
}
.popup-fields {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 6px;
}
.popup-field-label {
  font-size: 0.7rem;
  color: #6b7280;
  padding: 1px 8px 1px 0;
  white-space: nowrap;
  vertical-align: top;
}
.popup-field-value {
  font-size: 0.75rem;
  color: #111827;
  padding: 1px 0;
  word-break: break-word;
}
.popup-coords {
  font-size: 0.7rem;
  color: #9ca3af;
  margin-bottom: 4px;
}
.popup-open-link {
  font-size: 0.75rem;
  color: #2563eb;
  text-decoration: none;
  display: block;
}
.popup-open-link:hover {
  text-decoration: underline;
}

/* Fix sub-pixel gaps between tiles */
.leaflet-tile-container {
  transform: translateZ(0);
  will-change: transform;
}
.leaflet-tile {
  border-right: 1px solid transparent;
  border-bottom: 1px solid transparent;
}

/* ── Print area selector ──────────────────────────────────────────────────── */

/* Dark vignette outside the selected rectangle */
.print-rect-box {
  box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.52);
}

/* Resize handle base */
.print-handle {
  position: absolute;
  width: 10px;
  height: 10px;
  background: white;
  border: 2px solid #333;
  border-radius: 2px;
  z-index: 10;
}

/* Corners */
.handle-nw { top: -5px;  left: -5px;  cursor: nw-resize; }
.handle-ne { top: -5px;  right: -5px; cursor: ne-resize; }
.handle-se { bottom: -5px; right: -5px; cursor: se-resize; }
.handle-sw { bottom: -5px; left: -5px;  cursor: sw-resize; }

/* Edge midpoints */
.handle-n  { top: -5px;    left: calc(50% - 5px); cursor: n-resize; }
.handle-s  { bottom: -5px; left: calc(50% - 5px); cursor: s-resize; }
.handle-e  { right: -5px;  top:  calc(50% - 5px); cursor: e-resize; }
.handle-w  { left: -5px;   top:  calc(50% - 5px); cursor: w-resize; }

/* Print styles are handled by leaflet.browser.print plugin */
@page { margin: 0; }
</style>
