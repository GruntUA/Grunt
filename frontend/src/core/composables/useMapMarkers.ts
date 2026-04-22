import { ref, type Ref } from 'vue'
import L from 'leaflet'
import { docsApi } from '@/core/api/docs'
import type { ActiveFilter, DocField } from '@/types'
import { getIconPaths, createIcon } from '@/core/map/iconCache'
import { buildPopupTableHtml } from '@/core/map/popupFormatter'

interface UseMapMarkersParams {
  doctypeName: Ref<string>
  geoField: Ref<string>
  search: Ref<string | undefined>
  filters: Ref<ActiveFilter[] | undefined>
  labelField: Ref<string>
  colorField: Ref<string | null>
  colorMap: Ref<Record<string, string>>
  defaultColor: Ref<string>
  iconField: Ref<string | null>
  popupFields: Ref<DocField[]>
  getMap: () => L.Map | null
  getMarkerLayer: () => L.LayerGroup | null
  onOpenDoc: (id: string) => void
}

interface LoadedRow {
  row: Record<string, unknown>
  lat: number
  lng: number
}

export function useMapMarkers({
  doctypeName,
  geoField,
  search,
  filters,
  labelField,
  colorField,
  colorMap,
  defaultColor,
  iconField,
  popupFields,
  getMap,
  getMarkerLayer,
  onOpenDoc,
}: UseMapMarkersParams) {
  const isLoading = ref(false)
  const markerCount = ref(0)
  const skippedCount = ref(0)
  const loadedRows = ref<LoadedRow[]>([])

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

  async function loadMarkers() {
    const map = getMap()
    if (!map) return

    isLoading.value = true
    getMarkerLayer()?.clearLayers()
    loadedRows.value = []

    try {
      const fields = new Set([geoField.value, labelField.value, 'name', 'id'])
      if (colorField.value) {
        // "object_type__color" → request base field "object_type"; backend injects __color
        const baseField = colorField.value.includes('__')
          ? colorField.value.split('__')[0]
          : colorField.value
        fields.add(baseField)
      }
      popupFields.value.forEach((f) => fields.add(f.fieldname))

      const result = await docsApi.list(doctypeName.value, {
        page: 1,
        per_page: 5000,
        fields: [...fields].join(','),
        search: search.value || undefined,
        filters: filters.value?.length ? filters.value : undefined,
      })

      // Pre-render all unique icon paths before building markers
      const rows = result.data as Record<string, unknown>[]
      if (iconField.value) {
        const uniqueIcons = [
          ...new Set(rows.map((r) => String(r[iconField.value!] ?? '')).filter(Boolean)),
        ]
        await Promise.all(uniqueIcons.map((name) => getIconPaths(name)))
      }

      const bounds: L.LatLngTuple[] = []
      let skipped = 0

      for (const row of rows) {
        const geo = row[geoField.value]
        if (!geo || typeof geo !== 'object') {
          skipped++
          continue
        }
        const { lat, lng } = geo as Record<string, unknown>
        if (lat == null || lng == null) {
          skipped++
          continue
        }
        const latN = Number(lat)
        const lngN = Number(lng)
        if (isNaN(latN) || isNaN(lngN)) {
          skipped++
          continue
        }

        loadedRows.value.push({ row, lat: latN, lng: lngN })
        const color = resolveColor(row)
        const iconName = iconField.value ? String(row[iconField.value] ?? '') : ''
        const iconPaths = iconName ? await getIconPaths(iconName) : ''
        const icon = createIcon(color, iconPaths || undefined)
        const label = String(row[labelField.value] ?? row.name ?? '')

        const tableHtml = buildPopupTableHtml(row, popupFields.value, labelField.value)

        const marker = L.marker([latN, lngN], { icon })
        marker.bindPopup(
          `<div class="popup-title">${label}</div>
         ${tableHtml}
         <div class="popup-coords">${latN.toFixed(6)}, ${lngN.toFixed(6)}</div>
         <a href="#" data-id="${String(row.id ?? row.name)}"
            class="popup-open-link open-doc">
           Відкрити →
         </a>`,
          { maxWidth: 280 },
        )
        marker.on('popupopen', () => {
          const el = marker.getPopup()?.getElement()
          el?.querySelector('.open-doc')?.addEventListener('click', (e) => {
            e.preventDefault()
            const id = (e.currentTarget as HTMLElement).dataset.id
            if (id) onOpenDoc(id)
          })
        })

        getMarkerLayer()?.addLayer(marker)
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

  return {
    isLoading,
    markerCount,
    skippedCount,
    loadedRows,
    loadMarkers,
  }
}
