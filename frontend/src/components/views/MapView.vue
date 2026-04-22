<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { MapPin, Loader2 } from '@lucide/vue'
import type { DocType, DocTypeMapView, ScriptMenuItem, ActiveFilter } from '@/types'
import { useMapExport } from '@/core/composables/useMapExport'
import { useMapPrint, PRINT_FORMATS } from '@/core/composables/useMapPrint'
import { useMapPopupFields } from '@/core/composables/useMapPopupFields'
import { useMapCoordinateJump } from '@/core/composables/useMapCoordinateJump'
import { useMapMarkers } from '@/core/composables/useMapMarkers'
import { useMapLifecycle } from '@/core/composables/useMapLifecycle'

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

const doctypeName = computed(() => props.doctype.name)
const geoFieldName = computed(() => props.geoField)

// ── Popup fields (user-configured columns or in_list_view fallback) ───────────
const { popupFields } = useMapPopupFields({
  doctypeName,
  fields: computed(() => props.doctype.fields),
  geoField: geoFieldName,
})

// ── State ────────────────────────────────────────────────────────────────────
const router = useRouter()
const mapEl = ref<HTMLDivElement | null>(null)
const mapWrapEl = ref<HTMLDivElement | null>(null)

function navigateToDoc(id: string) {
  const ws = props.workspace ?? 'grunt'
  router.push(`/${ws}/${props.doctype.name}/${id}`)
}

const { isLoading, markerCount, skippedCount, loadedRows, loadMarkers } = useMapMarkers({
  doctypeName,
  geoField: geoFieldName,
  search: computed(() => props.search),
  filters: computed(() => props.filters),
  labelField,
  colorField,
  colorMap,
  defaultColor,
  iconField,
  popupFields,
  getMap: () => map.value,
  getMarkerLayer: () => markerLayer.value,
  onOpenDoc: navigateToDoc,
})

// Coordinate jump
const { coordInput, coordError, gotoCoord, clearCoordMarker } = useMapCoordinateJump({
  getMap: () => map.value,
})

// ── Export / Print ───────────────────────────────────────────────────────────
const { exportGeoJSON, exportCSV } = useMapExport({
  doctypeName,
  geoField: geoFieldName,
  labelField,
  colorField,
  loadedRows,
})

const {
  isPrintMode,
  printFormat,
  printRect,
  enterPrintMode,
  cancelPrint,
  confirmPrint,
  startMove,
  startResize,
} = useMapPrint({
  mapWrapEl,
  getMap: () => map.value,
  getBrowserPrint: () => browserPrint.value,
})

function exportPrint() {
  enterPrintMode()
}

// Menu items for toolbar
const menuItems: ScriptMenuItem[] = [
  { label: 'Експорт GeoJSON', action: exportGeoJSON, separator_before: true },
  { label: 'Експорт CSV', action: exportCSV },
  { label: 'Друк / PDF', action: exportPrint },
]

// ── Lifecycle ─────────────────────────────────────────────────────────────────
// Initialize map, tile layer, menu registration, and watch for prop changes
const { map, markerLayer, browserPrint } = useMapLifecycle({
  mapEl,
  menuItems,
  onRegisterMenuItems: (items) => emit('register-menu-items', items),
  onUnregisterMenuItems: (items) => emit('unregister-menu-items', items),
  onLoadMarkers: loadMarkers,
  geoField: geoFieldName,
  search: computed(() => props.search),
  filters: computed(() => props.filters),
})
</script>

<template>
  <div class="flex flex-col h-[calc(100vh-14rem)] rounded-3xl overflow-hidden shadow-2xl ring-1 ring-border/40 bg-card/30 backdrop-blur-md">
    <!-- Toolbar -->
    <div class="flex items-center justify-between px-5 py-3 bg-card/50 border-b border-border/40 shrink-0 gap-4">
      <div class="flex items-center gap-3 text-sm text-muted-foreground shrink-0">
        <div class="size-8 rounded-xl bg-primary/10 flex items-center justify-center border border-primary/20">
          <MapPin class="size-4 text-primary" />
        </div>
        <div class="flex flex-col">
          <span v-if="isLoading" class="flex items-center gap-2 font-bold text-foreground/80">
            <Loader2 class="size-3.5 animate-spin text-primary" /> Завантаження...
          </span>
          <span v-else class="font-bold text-foreground/80 lowercase">
            {{ markerCount }} мітк{{ markerCount === 1 ? 'а' : markerCount < 5 ? 'и' : '' }}
          </span>
          <span v-if="skippedCount && !isLoading" class="text-[10px] text-muted-foreground/60 font-medium">
            {{ skippedCount }} без координат
          </span>
        </div>
      </div>

      <!-- Coordinate jump input -->
      <div class="flex items-center gap-2 flex-1 max-w-sm relative">
        <div class="relative w-full group">
          <InputText
            v-model="coordInput"
            placeholder="46.8441, 35.4025"
            class="!h-10 !w-full !rounded-xl !pl-3 !pr-10 !text-xs !bg-background/40 hover:!bg-background !border-border/40 focus:!ring-1 focus:!ring-primary/20 transition-all shadow-inner-sm"
            :class="{ '!border-destructive/50': coordError }"
            @keydown.enter="gotoCoord"
            @input="coordError = false"
          />
          <div class="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-1">
            <Button v-if="coordInput" icon="pi pi-times" text rounded size="small" class="!size-6 !text-muted-foreground/40" @click="clearCoordMarker" />
            <Button icon="pi pi-search" text rounded size="small" class="!size-7 !text-primary/60 group-hover:!text-primary" @click="gotoCoord" />
          </div>
        </div>
      </div>

      <div class="flex items-center gap-1.5 shrink-0">
        <Button icon="pi pi-refresh" :loading="isLoading" @click="loadMarkers" rounded text class="!size-9 !text-muted-foreground/60 hover:!text-primary" />
        <Button icon="pi pi-print" @click="exportPrint" rounded text class="!size-9 !text-muted-foreground/60 hover:!text-primary" />
      </div>
    </div>

    <!-- Map container + print overlay wrapper -->
    <div ref="mapWrapEl" class="flex-1 w-full relative">
      <div ref="mapEl" class="absolute inset-0 z-0" />

      <!-- ── Print area selector ── -->
      <template v-if="isPrintMode">
        <!-- Dark overlay with "hole" via box-shadow on the rect -->
        <div class="absolute inset-0 z-[2000] select-none backdrop-blur-[2px]" @mousedown.self.prevent>

          <!-- Format selector bar -->
          <div class="absolute top-4 left-1/2 -translate-x-1/2 z-10
                      flex items-center gap-3 px-4 py-2
                      bg-foreground/90 text-background text-xs rounded-2xl shadow-2xl backdrop-blur-xl border border-white/10">
            <span class="opacity-60 font-bold uppercase tracking-wider text-[10px]">Формат:</span>
            <div class="flex bg-background/10 p-1 rounded-xl gap-1">
              <button v-for="(fmt, key) in PRINT_FORMATS" :key="key"
                      class="px-3 py-1 rounded-lg transition-all text-[10px] font-bold uppercase tracking-wide"
                      :class="printFormat === key
                        ? 'bg-background text-foreground shadow-sm'
                        : 'opacity-50 hover:opacity-100 hover:bg-background/5'"
                      @click="printFormat = key">
                {{ fmt.label.split(' ')[0] }}
              </button>
            </div>
            <div class="w-px h-6 bg-background/20 mx-1" />
            <Button label="Надрукувати" size="small" severity="primary" @click="confirmPrint" class="!rounded-xl !px-4 !h-8 !text-[11px] !font-bold" />
            <Button label="Скасувати" size="small" text @click="cancelPrint" class="!text-background !rounded-xl !h-8 !text-[11px]" />
          </div>

          <!-- Selection rectangle -->
          <div class="print-rect-box absolute cursor-move border-2 border-primary shadow-[0_0_0_9999px_rgba(0,0,0,0.6)]"
               :style="{
                 left:   printRect.x + 'px',
                 top:    printRect.y + 'px',
                 width:  printRect.w + 'px',
                 height: printRect.h + 'px',
               }"
               @mousedown.stop="startMove">

            <!-- Size label bar -->
            <div class="absolute -top-10 left-1/2 -translate-x-1/2 flex items-center gap-2
                        bg-primary text-primary-foreground text-[10px] font-black uppercase tracking-widest px-3 py-1.5 rounded-full shadow-lg">
              <i class="pi pi-expand text-[10px]" />
              {{ Math.round(printRect.w) }} × {{ Math.round(printRect.h) }} px
            </div>

            <!-- 8 resize handles -->
            <div v-for="h in (['nw','n','ne','e','se','s','sw','w'] as const)" :key="h"
                 class="print-handle !bg-primary !border-2 !border-white shadow-md !rounded-full !size-3"
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
