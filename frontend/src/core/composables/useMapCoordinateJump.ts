import { ref } from 'vue'
import L from 'leaflet'
import i18n from '@/plugins/i18n'

const t = (key: string): string => i18n.global.t(key)

interface UseMapCoordinateJumpParams {
  getMap: () => L.Map | null
}

export function useMapCoordinateJump({ getMap }: UseMapCoordinateJumpParams) {
  const coordInput = ref('')
  const coordError = ref(false)
  let coordMarker: L.Marker | null = null

  function gotoCoord() {
    coordError.value = false
    const raw = coordInput.value.trim()
    if (!raw) return

    // Accept "lat,lng" or "lat, lng" or "lat lng" or "lat;lng"
    const parts = raw
      .split(/[\s,;]+/)
      .map((s) => s.trim())
      .filter(Boolean)
    if (parts.length < 2) {
      coordError.value = true
      return
    }
    const lat = parseFloat(parts[0])
    const lng = parseFloat(parts[1])
    if (isNaN(lat) || isNaN(lng) || lat < -90 || lat > 90 || lng < -180 || lng > 180) {
      coordError.value = true
      return
    }

    const map = getMap()
    if (!map) return

    // Remove previous coord marker
    if (coordMarker) {
      coordMarker.remove()
      coordMarker = null
    }

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
      .bindPopup(`<div class="popup-title">📍 ${t('Marked point')}</div>
      <div class="popup-coords">${lat.toFixed(6)}, ${lng.toFixed(6)}</div>`)
      .openPopup()

    map.flyTo([lat, lng], 15, { duration: 1.2 })
  }

  function clearCoordMarker() {
    if (coordMarker) {
      coordMarker.remove()
      coordMarker = null
    }
    coordInput.value = ''
    coordError.value = false
  }

  return {
    coordInput,
    coordError,
    gotoCoord,
    clearCoordMarker,
  }
}
