import type { Ref } from 'vue'

interface LoadedRow {
  row: Record<string, unknown>
  lat: number
  lng: number
}

interface UseMapExportParams {
  doctypeName: Ref<string>
  geoField: Ref<string>
  labelField: Ref<string>
  colorField: Ref<string | null>
  loadedRows: Ref<LoadedRow[]>
}

export function useMapExport({ doctypeName, geoField, labelField, colorField, loadedRows }: UseMapExportParams) {
  function exportGeoJSON() {
    const features = loadedRows.value.map(({ row, lat, lng }) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [lng, lat] },
      properties: Object.fromEntries(Object.entries(row).filter(([k]) => k !== geoField.value)),
    }))
    downloadBlob(
      JSON.stringify({ type: 'FeatureCollection', features }, null, 2),
      `${doctypeName.value}_map.geojson`,
      'application/geo+json',
    )
  }

  function exportCSV() {
    const fields = new Set([labelField.value, 'name'])
    if (colorField.value) fields.add(colorField.value)
    const headers = ['lat', 'lng', ...fields]
    const lines = [
      headers.join(','),
      ...loadedRows.value.map(({ row, lat, lng }) =>
        [lat, lng, ...[...fields].map((f) => csvEscape(String(row[f] ?? '')))].join(','),
      ),
    ]
    downloadBlob(lines.join('\n'), `${doctypeName.value}_map.csv`, 'text/csv')
  }

  function csvEscape(v: string) {
    return v.includes(',') || v.includes('"') || v.includes('\n') ? `"${v.replace(/"/g, '""')}"` : v
  }

  function downloadBlob(content: string, filename: string, mime: string) {
    const blob = new Blob([content], { type: mime })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  return {
    exportGeoJSON,
    exportCSV,
    downloadBlob,
  }
}
