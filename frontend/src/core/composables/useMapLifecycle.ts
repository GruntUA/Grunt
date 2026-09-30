import { ref, Ref, onMounted, onUnmounted, watch, ComputedRef } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import 'leaflet.browser.print/dist/leaflet.browser.print.min.js'
import type { ScriptMenuItem, ActiveFilter } from '@/types'

/**
 * Manages Leaflet map lifecycle: initialization, tile layer setup, menu registration,
 * and cleanup on component unmount. Also handles reactive reloads on prop changes.
 */
export function useMapLifecycle(options: {
  mapEl: Ref<HTMLDivElement | null>
  menuItems: ScriptMenuItem[]
  onRegisterMenuItems: (items: ScriptMenuItem[]) => void
  onUnregisterMenuItems: (items: ScriptMenuItem[]) => void
  onLoadMarkers: () => void
  geoField: ComputedRef<string>
  search: ComputedRef<string | undefined>
  filters: ComputedRef<ActiveFilter[] | undefined>
}) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const map = ref<any>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const markerLayer = ref<any>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const browserPrint = ref<any>(null)

  // Initialize Leaflet map with tile layer and marker layer
  onMounted(() => {
    if (!options.mapEl.value) return

    // Create map instance
    map.value = L.map(options.mapEl.value, {
      center: [49.0, 32.0],
      zoom: 6,
      zoomControl: true,
    })

    // Add OSM tile layer
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a>',
      maxZoom: 19,
    }).addTo(map.value)

    // Create marker layer for later population
    markerLayer.value = L.layerGroup().addTo(map.value)

    // Initialize browser print plugin
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    browserPrint.value = (L as any).browserPrint(map.value, { documentTitle: '' })

    // Register menu items (export, print)
    options.onRegisterMenuItems(options.menuItems)

    // Load initial markers
    options.onLoadMarkers()
  })

  // Cleanup: unregister menu items and remove map
  onUnmounted(() => {
    options.onUnregisterMenuItems(options.menuItems)
    map.value?.remove()
    map.value = null
    markerLayer.value = null
    browserPrint.value = null
  })

  // Re-load markers when key props change
  watch(() => options.geoField.value, options.onLoadMarkers)
  watch(() => options.search.value, options.onLoadMarkers)
  watch(() => options.filters.value, options.onLoadMarkers, { deep: true })

  return {
    map,
    markerLayer,
    browserPrint,
  }
}
