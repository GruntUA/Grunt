<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { MapPin, RefreshCw, Loader2 } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { docsApi } from '@/core/api/docs'
import type { DocType, DocTypeMapView, ScriptMenuItem } from '@/types'

// ── Props ────────────────────────────────────────────────────────────────────
const props = defineProps<{
  doctype: DocType
  geoField: string
  workspace?: string
  search?: string
  filters?: Record<string, string>
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

let map: L.Map | null = null
let markerLayer: L.LayerGroup | null = null

// ── Marker helpers ────────────────────────────────────────────────────────────
function resolveColor(row: Record<string, unknown>): string {
  if (colorField.value) {
    const val = String(row[colorField.value] ?? '')
    if (colorMap.value[val]) return colorMap.value[val]
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

function createIcon(color: string): L.DivIcon {
  // Teardrop/pin SVG — easy to customize later
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 32" width="24" height="32">
    <path d="M12 0C5.373 0 0 5.373 0 12c0 9 12 20 12 20s12-11 12-20C24 5.373 18.627 0 12 0z"
      fill="${color}" stroke="white" stroke-width="1.5"/>
    <circle cx="12" cy="12" r="5" fill="white" opacity="0.85"/>
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
    if (colorField.value) fields.add(colorField.value)
    popupFields.value.forEach(f => fields.add(f.fieldname))

    const result = await docsApi.list(props.doctype.name, {
      page: 1,
      per_page: 5000,
      fields: [...fields].join(','),
      search: props.search || undefined,
      filters: props.filters && Object.keys(props.filters).length ? props.filters : undefined,
    })

    const bounds: L.LatLngTuple[] = []
    let skipped = 0

    for (const row of result.data as Record<string, unknown>[]) {
      const geo = row[props.geoField]
      if (!geo || typeof geo !== 'object') { skipped++; continue }
      const { lat, lng } = geo as Record<string, unknown>
      if (lat == null || lng == null) { skipped++; continue }
      const latN = Number(lat)
      const lngN = Number(lng)
      if (isNaN(latN) || isNaN(lngN)) { skipped++; continue }

      loadedRows.value.push({ row, lat: latN, lng: lngN })
      const color = resolveColor(row)
      const icon = createIcon(color)
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

function exportPrint() {
  window.print()
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
  loadMarkers()
  emit('register-menu-items', menuItems)
})

onUnmounted(() => {
  emit('unregister-menu-items', menuItems)
  map?.remove()
  map = null
  markerLayer = null
})

watch(() => props.geoField, loadMarkers)
watch(() => props.search, loadMarkers)
watch(() => props.filters, loadMarkers, { deep: true })
</script>

<template>
  <div class="flex flex-col h-[calc(100vh-14rem)] rounded-xl overflow-hidden shadow-md ring-1 ring-border/60">
    <!-- Toolbar -->
    <div class="flex items-center justify-between px-4 py-2 bg-card border-b border-border/60 shrink-0">
      <div class="flex items-center gap-2 text-sm text-muted-foreground">
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

      <Button variant="ghost" size="sm" class="h-8 w-8 p-0" :disabled="isLoading" @click="loadMarkers">
        <RefreshCw class="size-3.5" :class="{ 'animate-spin': isLoading }" />
      </Button>
    </div>

    <!-- Map container -->
    <div ref="mapEl" class="flex-1 w-full" />
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

/* Print styles */
@media print {
  body > *:not(.leaflet-container) { display: none !important; }
  .leaflet-container { position: fixed !important; inset: 0 !important; height: 100vh !important; }
}
</style>
