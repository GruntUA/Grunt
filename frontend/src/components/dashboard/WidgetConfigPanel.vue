<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DashboardWidget, WidgetType, WidgetAggregation, WidgetPeriod, WidgetCols, ShortcutItem } from '@/types'
import type { WorkspaceLinkItem } from '@/core/api/workspace'
import { docsApi } from '@/core/api'
import { reportsApi } from '@/core/api/reports'
import type { LinkSearchItem } from '@/core/api/docs'
import type { ReportSummary } from '@/types'
import { useDocTypeStore } from '@/stores/doctype'
import { Plus, Trash2 } from '@lucide/vue'

const props = defineProps<{ widget: DashboardWidget | null }>()
const emit = defineEmits<{
  change: [widget: DashboardWidget]
  remove: []
}>()

const { t } = useI18n()
const dtStore = useDocTypeStore()
dtStore.loadAll()

const draft = ref<DashboardWidget | null>(null)

// Report list for chart/donut widgets that source their data from a saved Report.
const reports = ref<ReportSummary[]>([])
let reportsLoaded = false
async function ensureReports() {
  if (reportsLoaded) return
  reportsLoaded = true
  try { reports.value = await reportsApi.list() } catch { reports.value = [] }
}

// ── Links editor ─────────────────────────────────────────────────────────────

const linkItems = ref<WorkspaceLinkItem[]>([])

function syncLinksFromContent(content: string | null | undefined) {
  try { linkItems.value = JSON.parse(content ?? '[]') } catch { linkItems.value = [] }
}

// ── Tile list editor (shortcuts_grid) ─────────────────────────────────────────

const tiles = ref<ShortcutItem[]>([])

function syncTilesFromContent(content: string | null | undefined) {
  try { tiles.value = JSON.parse(content ?? '[]') } catch { tiles.value = [] }
}

watch(() => props.widget, (w) => {
  // Reset draft only when switching to a different widget, not on parent sync-back
  if (!w) {
    draft.value = null
    tiles.value = []
    linkItems.value = []
  } else if (draft.value?.id !== w.id) {
    draft.value = { ...w }
    syncTilesFromContent(w.content)
    syncLinksFromContent(w.content)
  }
  if (w && (w.widget_type === 'chart_area' || w.widget_type === 'chart_bar' || w.widget_type === 'donut')) {
    ensureReports()
  }
}, { immediate: true })

function apply() {
  if (draft.value) emit('change', { ...draft.value })
}

// ── Constants ────────────────────────────────────────────────────────────────

const WIDGET_TYPES = computed<{ value: WidgetType; label: string; icon: string }[]>(() => [
  { value: 'metric',         label: t('Metric'),        icon: '🔢' },
  { value: 'gauge',          label: t('Gauge'),         icon: '🎯' },
  { value: 'chart_area',     label: 'Area',             icon: '📈' },
  { value: 'chart_bar',      label: 'Bar',              icon: '📊' },
  { value: 'donut',          label: t('Donut'),         icon: '🍩' },
  { value: 'list',           label: t('List'),          icon: '📋' },
  { value: 'shortcut',       label: t('Shortcut'),      icon: '🔗' },
  { value: 'shortcuts_grid', label: t('Shortcuts grid'), icon: '⊞' },
  { value: 'text',           label: t('Text'),          icon: '📝' },
  { value: 'clock',          label: t('Clock'),         icon: '🕐' },
  { value: 'activity',       label: t('Activity'),      icon: '🕒' },
  { value: 'calendar',       label: t('Calendar'),      icon: '📅' },
  { value: 'heatmap',        label: t('Heatmap'),       icon: '🟩' },
  { value: 'funnel',         label: t('Funnel'),        icon: '🔽' },
  { value: 'table',          label: t('Table'),         icon: '📊' },
  { value: 'links',          label: t('Links'),         icon: '🔗' },
])

const AGGREGATIONS = computed<{ value: WidgetAggregation; label: string }[]>(() => [
  { value: 'count', label: t('Count (COUNT)') },
  { value: 'sum',   label: t('Sum (SUM)') },
  { value: 'avg',   label: t('Average (AVG)') },
  { value: 'min',   label: t('Minimum') },
  { value: 'max',   label: t('Maximum') },
])

const PERIODS = computed<{ value: WidgetPeriod; label: string }[]>(() => [
  { value: '7d',   label: t('7 days') },
  { value: '30d',  label: t('30 days') },
  { value: '90d',  label: t('3 months') },
  { value: '365d', label: t('Year') },
])

const COLS = computed<{ value: WidgetCols; label: string }[]>(() => [
  { value: 1, label: '1/4' },
  { value: 2, label: '1/2' },
  { value: 3, label: '3/4' },
  { value: 4, label: t('Full') },
])

const COLORS = computed(() => [
  { value: 'primary', label: t('Green'),    bg: '#2D6A4F' },
  { value: 'blue',    label: t('Blue'),     bg: '#3b82f6' },
  { value: 'amber',   label: t('Yellow'),   bg: '#f59e0b' },
  { value: 'red',     label: t('Red'),      bg: '#ef4444' },
  { value: 'violet',  label: t('Violet'),   bg: '#8b5cf6' },
  { value: 'cyan',    label: t('Cyan'),     bg: '#06b6d4' },
])

const LINK_TYPES = computed(() => [
  { value: 'DocType',   label: t('DocType (list)') },
  { value: 'Report',    label: t('Report') },
  { value: 'Page', label: t('Page') },
  { value: 'URL',       label: t('External URL') },
])

// ── Computed flags ────────────────────────────────────────────────────────────

const isChart        = computed(() => draft.value?.widget_type === 'chart_area' || draft.value?.widget_type === 'chart_bar')
const isDonut        = computed(() => draft.value?.widget_type === 'donut')
const supportsReportSource = computed(() => isChart.value || isDonut.value)
// `report == null` → doctype-aggregate source; `report === ''` → report source, none picked yet.
const isReportSourced = computed(() => supportsReportSource.value && draft.value?.report != null)

function setReportSource(useReport: boolean) {
  if (!draft.value) return
  draft.value.report = useReport ? (draft.value.report ?? '') : null
  apply()
}
const isList         = computed(() => draft.value?.widget_type === 'list')
const isMetric       = computed(() => draft.value?.widget_type === 'metric')
const isGauge        = computed(() => draft.value?.widget_type === 'gauge')
const isShortcut     = computed(() => draft.value?.widget_type === 'shortcut')
const isShortcutsGrid = computed(() => draft.value?.widget_type === 'shortcuts_grid')
const isText         = computed(() => draft.value?.widget_type === 'text')
const isClock        = computed(() => draft.value?.widget_type === 'clock')
const isActivity     = computed(() => draft.value?.widget_type === 'activity')
const isCalendar     = computed(() => draft.value?.widget_type === 'calendar')
const isHeatmap      = computed(() => draft.value?.widget_type === 'heatmap')
const isFunnel       = computed(() => draft.value?.widget_type === 'funnel')
const isTableWidget  = computed(() => draft.value?.widget_type === 'table')
const isLinks        = computed(() => draft.value?.widget_type === 'links')
const isDataWidget   = computed(() =>
  isMetric.value || isGauge.value || isChart.value || isDonut.value || isList.value ||
  isCalendar.value || isHeatmap.value || isFunnel.value || isTableWidget.value
)
const needsField = computed(() =>
  draft.value ? ['sum', 'avg', 'min', 'max'].includes(draft.value.aggregation) : false
)

// ── Shortcut link-search autocomplete ───────────────────────────────────────

const linkQuery = ref('')
const linkResults = ref<LinkSearchItem[]>([])
const linkOpen = ref(false)
let linkTimer: ReturnType<typeof setTimeout>
let linkBlurTimer: ReturnType<typeof setTimeout>

const linkSearchDoctype = computed(() => {
  if (!isShortcut.value || !draft.value) return null
  const lt = draft.value.link_type
  return (lt === 'DocType' || lt === 'Report' || lt === 'Page') ? lt : null
})

watch(() => draft.value?.doctype, (v) => {
  if (isShortcut.value) linkQuery.value = v ?? ''
}, { immediate: true })

watch(linkSearchDoctype, () => {
  if (draft.value) linkQuery.value = draft.value.doctype ?? ''
})

async function onLinkInput(val: string) {
  linkQuery.value = val
  if (draft.value) { draft.value = { ...draft.value, doctype: val }; apply() }
  if (!linkSearchDoctype.value) return
  clearTimeout(linkTimer)
  linkTimer = setTimeout(async () => {
    try {
      linkResults.value = await docsApi.linkSearch(linkSearchDoctype.value!, val)
      linkOpen.value = true
    } catch { linkResults.value = [] }
  }, val ? 250 : 0)
}

async function onLinkFocus() {
  clearTimeout(linkBlurTimer)
  if (!linkSearchDoctype.value) return
  try {
    linkResults.value = await docsApi.linkSearch(linkSearchDoctype.value, linkQuery.value)
    linkOpen.value = true
  } catch { linkResults.value = [] }
}

function onLinkBlur() {
  linkBlurTimer = setTimeout(() => { linkOpen.value = false }, 200)
}

function selectLink(item: LinkSearchItem) {
  if (!draft.value) return
  draft.value = { ...draft.value, doctype: item.name }
  linkQuery.value = item.title
  linkOpen.value = false
  apply()
}

// ── Links editor setters ─────────────────────────────────────────────────────

function setLinks(val: WorkspaceLinkItem[]) {
  if (!draft.value) return
  linkItems.value = val
  draft.value = { ...draft.value, content: JSON.stringify(val) }
  apply()
}

function addLink() {
  setLinks([...linkItems.value, { label: t('New'), icon: '', type: 'DocType', link_to: '' }])
}

function removeLink(i: number) {
  const arr = [...linkItems.value]
  arr.splice(i, 1)
  setLinks(arr)
}

function updateLink(i: number, key: keyof WorkspaceLinkItem, value: string) {
  const arr = linkItems.value.map((l, idx) => idx === i ? { ...l, [key]: value } : l)
  setLinks(arr)
}

// ── Tile list editor setters (shortcuts_grid) ─────────────────────────────────

function setTiles(val: ShortcutItem[]) {
  if (!draft.value) return
  tiles.value = val
  draft.value = { ...draft.value, content: JSON.stringify(val) }
  apply()
}

function addTile() {
  setTiles([...tiles.value, { title: t('New'), icon: 'Link', link_type: 'DocType', link_to: '', color: 'primary' }])
}

function removeTile(i: number) {
  const arr = [...tiles.value]
  arr.splice(i, 1)
  setTiles(arr)
}

function updateTile(i: number, key: keyof ShortcutItem, value: string) {
  const arr = tiles.value.map((t, idx) => idx === i ? { ...t, [key]: value } : t)
  setTiles(arr)
}
</script>

<template>
  <div v-if="!draft" class="flex flex-col items-center justify-center h-full gap-3 text-muted-foreground px-6">
    <div class="text-4xl">👈</div>
    <p class="text-center">{{ t('Select a widget on the canvas or add a new one from the palette') }}</p>
  </div>

  <div v-else class="flex flex-col h-full overflow-hidden">
    <div class="px-4 py-3 border-b shrink-0 flex items-center justify-between">
      <span class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{{ t('Settings') }}</span>
      <button
        class="text-xs text-destructive hover:underline flex items-center gap-1"
        @click="emit('remove')"
      >
        <Trash2 class="size-3" /> {{ t('Delete') }}
      </button>
    </div>

    <div class="flex-1 overflow-y-auto p-4 space-y-4">

      <!-- Widget type -->
      <div class="space-y-1.5">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">{{ t('Type') }}</label>
        <div class="grid grid-cols-2 gap-1">
          <button
            v-for="wt in WIDGET_TYPES" :key="wt.value"
            :class="[
              'flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border text-xs transition-colors',
              draft.widget_type === wt.value
                ? 'bg-primary text-primary-foreground border-primary'
                : 'hover:bg-muted border-border',
            ]"
            @click="draft.widget_type = wt.value; apply()"
          >
            <span>{{ wt.icon }}</span>{{ wt.label }}
          </button>
        </div>
      </div>

      <!-- Title -->
      <div class="space-y-1">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">{{ t('Title') }}</label>
        <input
          v-model="draft.title"
          class="w-full h-8 px-3 rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
          :placeholder="t('Widget title')"
          @change="apply"
        />
      </div>

      <!-- Data source: doctype aggregate vs saved Report (chart / donut) -->
      <div v-if="supportsReportSource" class="space-y-1">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">{{ t('Data source') }}</label>
        <select
          :value="isReportSourced ? 'report' : 'doctype'"
          class="w-full h-8 px-3 rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
          @change="setReportSource(($event.target as HTMLSelectElement).value === 'report')"
        >
          <option value="doctype">{{ t('DocType aggregate') }}</option>
          <option value="report">{{ t('Saved report') }}</option>
        </select>
        <select
          v-if="isReportSourced"
          v-model="draft.report"
          class="w-full h-8 px-3 mt-1 rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
          @change="apply"
        >
          <option value="">{{ t('— Select —') }}</option>
          <option v-for="r in reports" :key="r.name" :value="r.report_name">{{ r.report_name }}</option>
        </select>
      </div>

      <!-- DocType -->
      <div v-if="(isDataWidget && !isReportSourced) || isShortcut" class="space-y-1">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          {{ isShortcut ? t('Target') : 'DocType' }}
        </label>
        <!-- data widgets — static select -->
        <select
          v-if="isDataWidget && !isReportSourced"
          v-model="draft.doctype"
          class="w-full h-8 px-3 rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
          @change="apply"
        >
          <option value="">{{ t('— Select —') }}</option>
          <option v-for="dt in dtStore.doctypes.filter(d => !d.is_child)" :key="dt.name" :value="dt.name">
            {{ dt.label }}
          </option>
        </select>
        <!-- shortcut: link-search autocomplete (DocType / Report / Page) -->
        <div v-else-if="isShortcut && linkSearchDoctype" class="relative">
          <input
            :value="linkQuery"
            class="w-full h-8 px-3 rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
            :placeholder="t('Search {dt}...', { dt: linkSearchDoctype })"
            autocomplete="off"
            @input="onLinkInput(($event.target as HTMLInputElement).value)"
            @focus="onLinkFocus"
            @blur="onLinkBlur"
          />
          <div
            v-if="linkOpen && linkResults.length"
            class="absolute left-0 right-0 top-full mt-1 z-50 bg-popover border border-border rounded-md shadow-md max-h-48 overflow-y-auto"
          >
            <button
              v-for="item in linkResults"
              :key="item.name"
              type="button"
              class="w-full text-left px-3 py-1.5 hover:bg-accent/50 transition-colors"
              @mousedown.prevent="selectLink(item)"
            >{{ item.title }}</button>
          </div>
        </div>
        <!-- shortcut: plain URL input -->
        <input
          v-else-if="isShortcut"
          v-model="draft.doctype"
          class="w-full h-8 px-3 rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
          placeholder="https://…"
          @change="apply"
        />
      </div>

      <!-- DocType filter (activity) -->
      <div v-if="isActivity" class="space-y-1">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          {{ t('Filter by DocType') }} <span class="normal-case font-normal">({{ t('optional') }})</span>
        </label>
        <select
          v-model="draft.doctype"
          class="w-full h-8 px-3 rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
          @change="apply"
        >
          <option value="">{{ t('— All —') }}</option>
          <option v-for="dt in dtStore.doctypes.filter(d => !d.is_child)" :key="dt.name" :value="dt.name">
            {{ dt.label }}
          </option>
        </select>
      </div>

      <!-- Link type (shortcut) -->
      <div v-if="isShortcut" class="space-y-1">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">{{ t('Link type') }}</label>
        <div class="grid grid-cols-2 gap-1">
          <button
            v-for="lt in LINK_TYPES" :key="lt.value"
            :class="[
              'px-2.5 py-1.5 rounded-md border text-xs transition-colors',
              draft.link_type === lt.value ? 'bg-primary text-primary-foreground border-primary' : 'hover:bg-muted',
            ]"
            @click="draft.link_type = lt.value as typeof draft.link_type; apply()"
          >{{ lt.label }}</button>
        </div>
      </div>

      <!-- Description (shortcut / clock) -->
      <div v-if="isShortcut || isClock" class="space-y-1">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          {{ isClock ? t('Note') : t('Subtitle') }}
        </label>
        <input
          v-model="draft.description"
          class="w-full h-8 px-3 rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
          @change="apply"
        />
      </div>

      <!-- Content (text widget) -->
      <div v-if="isText" class="space-y-1">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">{{ t('Content (HTML/text)') }}</label>
        <textarea
          v-model="draft.content"
          rows="5"
          class="w-full px-3 py-2 rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none font-mono"
          @change="apply"
        />
      </div>

      <!-- Shortcuts grid: tile list editor -->
      <div v-if="isShortcutsGrid" class="space-y-2">
        <div class="flex items-center justify-between">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">{{ t('Tiles') }}</label>
          <button
            class="flex items-center gap-1 text-xs text-primary hover:underline"
            @click="addTile"
          >
            <Plus class="size-3" /> {{ t('Add') }}
          </button>
        </div>
        <div v-if="tiles.length === 0" class="py-3 text-center text-xs text-muted-foreground border rounded-md">
          {{ t('No tiles — click «Add»') }}
        </div>
        <div
          v-for="(tile, i) in tiles"
          :key="i"
          class="rounded-md border bg-muted/30 p-3 space-y-2"
        >
          <div class="flex items-center justify-between">
            <span class="text-xs font-medium text-muted-foreground">{{ t('Tile {n}', { n: i + 1 }) }}</span>
            <button class="text-muted-foreground hover:text-destructive transition-colors" @click="removeTile(i)">
              <Trash2 class="size-3.5" />
            </button>
          </div>
          <input
            :value="tile.title"
            class="w-full h-7 px-2.5 rounded border bg-background text-xs focus:outline-none focus:ring-2 focus:ring-primary/30"
            :placeholder="t('Title')"
            @input="updateTile(i, 'title', ($event.target as HTMLInputElement).value)"
          />
          <div class="grid grid-cols-2 gap-1.5">
            <input
              :value="tile.icon"
              class="h-7 px-2.5 rounded border bg-background text-xs focus:outline-none focus:ring-2 focus:ring-primary/30"
              :placeholder="t('Icon (lucide)')"
              @input="updateTile(i, 'icon', ($event.target as HTMLInputElement).value)"
            />
            <select
              :value="tile.link_type"
              class="h-7 px-2 rounded border bg-background text-xs focus:outline-none"
              @change="updateTile(i, 'link_type', ($event.target as HTMLSelectElement).value)"
            >
              <option value="DocType">DocType</option>
              <option value="Report">{{ t('Report') }}</option>
              <option value="Page">Page</option>
              <option value="URL">URL</option>
            </select>
          </div>
          <select
            v-if="tile.link_type === 'DocType'"
            :value="tile.link_to"
            class="w-full h-7 px-2 rounded border bg-background text-xs focus:outline-none focus:ring-2 focus:ring-primary/30"
            @change="updateTile(i, 'link_to', ($event.target as HTMLSelectElement).value)"
          >
            <option value="">{{ t('— Select —') }}</option>
            <option v-for="dt in dtStore.doctypes.filter(d => !d.is_child)" :key="dt.name" :value="dt.name">{{ dt.label }}</option>
          </select>
          <input
            v-else
            :value="tile.link_to"
            class="w-full h-7 px-2.5 rounded border bg-background text-xs focus:outline-none focus:ring-2 focus:ring-primary/30"
            :placeholder="t('URL or name...')"
            @input="updateTile(i, 'link_to', ($event.target as HTMLInputElement).value)"
          />
          <!-- Tile color -->
          <div class="flex gap-1.5">
            <button
              v-for="c in COLORS" :key="c.value"
              :title="c.label"
              :class="['w-5 h-5 rounded-full border-2 transition-colors', tile.color === c.value ? 'border-foreground scale-110' : 'border-transparent']"
              :style="{ background: c.bg }"
              @click="updateTile(i, 'color', c.value)"
            />
          </div>
        </div>
      </div>

      <!-- Links editor -->
      <div v-if="isLinks" class="space-y-2">
        <div class="flex items-center justify-between">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">{{ t('Links') }}</label>
          <button class="flex items-center gap-1 text-xs text-primary hover:underline" @click="addLink">
            <Plus class="size-3" /> {{ t('Add') }}
          </button>
        </div>
        <div v-if="linkItems.length === 0" class="py-3 text-center text-xs text-muted-foreground border rounded-md">
          {{ t('No links') }}
        </div>
        <div v-for="(link, i) in linkItems" :key="i" class="rounded-md border bg-muted/30 p-3 space-y-2">
          <div class="flex items-center justify-between">
            <span class="text-xs font-medium text-muted-foreground">{{ t('Link {n}', { n: i + 1 }) }}</span>
            <button class="text-muted-foreground hover:text-destructive transition-colors" @click="removeLink(i)">
              <Trash2 class="size-3.5" />
            </button>
          </div>
          <div class="grid grid-cols-2 gap-1.5">
            <input :value="link.icon" class="h-7 px-2.5 rounded border bg-background text-xs focus:outline-none" placeholder="Emoji 📋" @input="updateLink(i, 'icon', ($event.target as HTMLInputElement).value)" />
            <select :value="link.type" class="h-7 px-2 rounded border bg-background text-xs focus:outline-none" @change="updateLink(i, 'type', ($event.target as HTMLSelectElement).value)">
              <option value="DocType">DocType</option>
              <option value="Report">{{ t('Report') }}</option>
              <option value="Page">Page</option>
              <option value="URL">URL</option>
            </select>
          </div>
          <input :value="link.label" class="w-full h-7 px-2.5 rounded border bg-background text-xs focus:outline-none" :placeholder="t('Title')" @input="updateLink(i, 'label', ($event.target as HTMLInputElement).value)" />
          <select
            v-if="link.type === 'DocType'"
            :value="link.link_to"
            class="w-full h-7 px-2 rounded border bg-background text-xs focus:outline-none focus:ring-2 focus:ring-primary/30"
            @change="updateLink(i, 'link_to', ($event.target as HTMLSelectElement).value)"
          >
            <option value="">{{ t('— Select —') }}</option>
            <option v-for="dt in dtStore.doctypes.filter(d => !d.is_child)" :key="dt.name" :value="dt.name">{{ dt.label }}</option>
          </select>
          <input
            v-else
            :value="link.link_to"
            class="w-full h-7 px-2.5 rounded border bg-background text-xs focus:outline-none"
            :placeholder="t('URL or name...')"
            @input="updateLink(i, 'link_to', ($event.target as HTMLInputElement).value)"
          />
          <input :value="link.description" class="w-full h-7 px-2.5 rounded border bg-background text-xs focus:outline-none" :placeholder="t('Description (optional)')" @input="updateLink(i, 'description', ($event.target as HTMLInputElement).value)" />
        </div>
      </div>

      <!-- Gauge range -->
      <template v-if="isGauge">
        <div class="grid grid-cols-2 gap-2">
          <div class="space-y-1">
            <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">{{ t('Min') }}</label>
            <input v-model.number="draft.min_value" type="number"
              class="w-full h-8 px-3 rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
              @change="apply" />
          </div>
          <div class="space-y-1">
            <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">{{ t('Max') }}</label>
            <input v-model.number="draft.max_value" type="number"
              class="w-full h-8 px-3 rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
              @change="apply" />
          </div>
        </div>
      </template>

      <!-- Aggregation (metric / gauge / table) -->
      <template v-if="isMetric || isGauge || isTableWidget">
        <div class="space-y-1">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">{{ t('Aggregation') }}</label>
          <div class="grid grid-cols-1 gap-1">
            <button
              v-for="a in AGGREGATIONS" :key="a.value"
              :class="[
                'px-3 py-1.5 rounded-md border text-xs transition-colors text-left',
                draft.aggregation === a.value ? 'bg-primary text-primary-foreground border-primary' : 'hover:bg-muted',
              ]"
              @click="draft.aggregation = a.value; apply()"
            >{{ a.label }}</button>
          </div>
        </div>
        <div v-if="needsField" class="space-y-1">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">{{ t('Field') }}</label>
          <input v-model="draft.field" class="w-full h-8 px-3 rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30" placeholder="fieldname" @change="apply" />
        </div>
      </template>

      <!-- Group by (chart / donut / funnel / table) -->
      <div v-if="(isChart || isDonut || isFunnel || isTableWidget) && !isReportSourced" class="space-y-1">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">{{ t('Group by') }}</label>
        <input v-model="draft.group_by" class="w-full h-8 px-3 rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30" placeholder="fieldname" @change="apply" />
      </div>

      <!-- Date field + period -->
      <template v-if="(isChart || isMetric || isGauge || isCalendar || isHeatmap || isFunnel || isTableWidget) && !isReportSourced">
        <div class="space-y-1">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">{{ t('Date field') }}</label>
          <input v-model="draft.date_field" class="w-full h-8 px-3 rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30" placeholder="created_at" @change="apply" />
        </div>
        <div class="space-y-1">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">{{ t('Period') }}</label>
          <div class="grid grid-cols-4 gap-1">
            <button
              v-for="p in PERIODS" :key="p.value"
              :class="[
                'py-1.5 rounded-md border text-xs transition-colors',
                draft.period === p.value ? 'bg-primary text-primary-foreground border-primary' : 'hover:bg-muted',
              ]"
              @click="draft.period = p.value; apply()"
            >{{ p.label }}</button>
          </div>
        </div>
      </template>

      <!-- Width -->
      <div class="space-y-1">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">{{ t('Width') }}</label>
        <div class="grid grid-cols-4 gap-1">
          <button
            v-for="c in COLS" :key="c.value"
            :class="[
              'py-1.5 rounded-md border text-xs transition-colors',
              draft.cols === c.value ? 'bg-primary text-primary-foreground border-primary' : 'hover:bg-muted',
            ]"
            @click="draft.cols = c.value; apply()"
          >{{ c.label }}</button>
        </div>
      </div>

      <!-- Color -->
      <div class="space-y-1">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">{{ t('Color') }}</label>
        <div class="flex gap-2">
          <button
            v-for="c in COLORS" :key="c.value"
            :title="c.label"
            :class="['w-7 h-7 rounded-full border-2 transition-colors', draft.color === c.value ? 'border-foreground scale-110' : 'border-transparent']"
            :style="{ background: c.bg }"
            @click="draft.color = c.value; apply()"
          />
        </div>
      </div>

      <!-- Icon -->
      <div v-if="isMetric || isShortcut" class="space-y-1">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">{{ t('Icon (lucide)') }}</label>
        <input v-model="draft.icon" class="w-full h-8 px-3 rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30" placeholder="BarChart2, Users..." @change="apply" />
      </div>

    </div>
  </div>
</template>
