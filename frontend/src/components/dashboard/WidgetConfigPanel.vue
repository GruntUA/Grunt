<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import type { DashboardWidget, WidgetType, WidgetAggregation, WidgetPeriod, WidgetCols, ShortcutItem } from '@/types'
import type { WorkspaceLinkItem } from '@/core/api/workspace'
import { useDocTypeStore } from '@/stores/doctype'
import { Plus, Trash2 } from 'lucide-vue-next'

const props = defineProps<{ widget: DashboardWidget | null }>()
const emit = defineEmits<{
  change: [widget: DashboardWidget]
  remove: []
}>()

const dtStore = useDocTypeStore()
dtStore.loadAll()

const draft = ref<DashboardWidget | null>(null)

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
}, { immediate: true })

function apply() {
  if (draft.value) emit('change', { ...draft.value })
}

// ── Constants ────────────────────────────────────────────────────────────────

const WIDGET_TYPES: { value: WidgetType; label: string; icon: string }[] = [
  { value: 'metric',         label: 'Метрика',       icon: '🔢' },
  { value: 'chart_area',     label: 'Area',          icon: '📈' },
  { value: 'chart_bar',      label: 'Bar',           icon: '📊' },
  { value: 'donut',          label: 'Кругова',       icon: '🍩' },
  { value: 'list',           label: 'Список',        icon: '📋' },
  { value: 'shortcut',       label: 'Ярлик',         icon: '🔗' },
  { value: 'shortcuts_grid', label: 'Сітка ярликів', icon: '⊞' },
  { value: 'text',           label: 'Текст',         icon: '📝' },
  { value: 'clock',          label: 'Годинник',      icon: '🕐' },
  { value: 'activity',       label: 'Активність',    icon: '🕒' },
  { value: 'calendar',       label: 'Календар',      icon: '📅' },
  { value: 'heatmap',        label: 'Теплокарта',    icon: '🟩' },
  { value: 'funnel',         label: 'Воронка',       icon: '🔽' },
  { value: 'table',          label: 'Таблиця',       icon: '📊' },
  { value: 'links',          label: 'Посилання',     icon: '🔗' },
]

const AGGREGATIONS: { value: WidgetAggregation; label: string }[] = [
  { value: 'count', label: 'Кількість (COUNT)' },
  { value: 'sum',   label: 'Сума (SUM)' },
  { value: 'avg',   label: 'Середнє (AVG)' },
  { value: 'min',   label: 'Мінімум' },
  { value: 'max',   label: 'Максимум' },
]

const PERIODS: { value: WidgetPeriod; label: string }[] = [
  { value: '7d',   label: '7 днів' },
  { value: '30d',  label: '30 днів' },
  { value: '90d',  label: '3 місяці' },
  { value: '365d', label: 'Рік' },
]

const COLS: { value: WidgetCols; label: string }[] = [
  { value: 1, label: '1/4' },
  { value: 2, label: '1/2' },
  { value: 3, label: '3/4' },
  { value: 4, label: 'Повна' },
]

const COLORS = [
  { value: 'primary', label: 'Зелений',    bg: '#2D6A4F' },
  { value: 'blue',    label: 'Синій',      bg: '#3b82f6' },
  { value: 'amber',   label: 'Жовтий',     bg: '#f59e0b' },
  { value: 'red',     label: 'Червоний',   bg: '#ef4444' },
  { value: 'violet',  label: 'Фіолетовий', bg: '#8b5cf6' },
  { value: 'cyan',    label: 'Блакитний',  bg: '#06b6d4' },
]

const LINK_TYPES = [
  { value: 'DocType',   label: 'DocType (список)' },
  { value: 'Report',    label: 'Звіт' },
  { value: 'Dashboard', label: 'Дашборд' },
  { value: 'URL',       label: 'Зовнішній URL' },
]

// ── Computed flags ────────────────────────────────────────────────────────────

const isChart        = computed(() => draft.value?.widget_type === 'chart_area' || draft.value?.widget_type === 'chart_bar')
const isDonut        = computed(() => draft.value?.widget_type === 'donut')
const isList         = computed(() => draft.value?.widget_type === 'list')
const isMetric       = computed(() => draft.value?.widget_type === 'metric')
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
  isMetric.value || isChart.value || isDonut.value || isList.value ||
  isCalendar.value || isHeatmap.value || isFunnel.value || isTableWidget.value
)
const needsField = computed(() =>
  draft.value ? ['sum', 'avg', 'min', 'max'].includes(draft.value.aggregation) : false
)

// ── Links editor setters ─────────────────────────────────────────────────────

function setLinks(val: WorkspaceLinkItem[]) {
  if (!draft.value) return
  linkItems.value = val
  draft.value = { ...draft.value, content: JSON.stringify(val) }
  apply()
}

function addLink() {
  setLinks([...linkItems.value, { label: 'Новий', icon: '', type: 'DocType', link_to: '' }])
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
  setTiles([...tiles.value, { title: 'Новий', icon: 'Link', link_type: 'DocType', link_to: '', color: 'primary' }])
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
    <p class="text-sm text-center">Оберіть віджет на полотні або додайте новий з палітри</p>
  </div>

  <div v-else class="flex flex-col h-full overflow-hidden">
    <div class="px-4 py-3 border-b shrink-0 flex items-center justify-between">
      <span class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Налаштування</span>
      <button
        class="text-xs text-destructive hover:underline flex items-center gap-1"
        @click="emit('remove')"
      >
        <Trash2 class="size-3" /> Видалити
      </button>
    </div>

    <div class="flex-1 overflow-y-auto p-4 space-y-4">

      <!-- Widget type -->
      <div class="space-y-1.5">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Тип</label>
        <div class="grid grid-cols-2 gap-1">
          <button
            v-for="t in WIDGET_TYPES" :key="t.value"
            :class="[
              'flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border text-xs transition-colors',
              draft.widget_type === t.value
                ? 'bg-primary text-primary-foreground border-primary'
                : 'hover:bg-muted border-border',
            ]"
            @click="draft.widget_type = t.value; apply()"
          >
            <span>{{ t.icon }}</span>{{ t.label }}
          </button>
        </div>
      </div>

      <!-- Title -->
      <div class="space-y-1">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Назва</label>
        <input
          v-model="draft.title"
          class="w-full h-8 px-3 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
          placeholder="Назва віджета"
          @change="apply"
        />
      </div>

      <!-- DocType -->
      <div v-if="isDataWidget || isShortcut" class="space-y-1">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          {{ isShortcut ? 'Ціль' : 'DocType' }}
        </label>
        <select
          v-if="isDataWidget"
          v-model="draft.doctype"
          class="w-full h-8 px-3 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
          @change="apply"
        >
          <option value="">— Виберіть —</option>
          <option v-for="dt in dtStore.doctypes.filter(d => !d.is_child)" :key="dt.name" :value="dt.name">
            {{ dt.label }}
          </option>
        </select>
        <input
          v-else
          v-model="draft.doctype"
          class="w-full h-8 px-3 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
          placeholder="DocType, Report, Dashboard або URL"
          @change="apply"
        />
      </div>

      <!-- DocType filter (activity) -->
      <div v-if="isActivity" class="space-y-1">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          Фільтр за DocType <span class="normal-case font-normal">(опціонально)</span>
        </label>
        <select
          v-model="draft.doctype"
          class="w-full h-8 px-3 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
          @change="apply"
        >
          <option value="">— Всі —</option>
          <option v-for="dt in dtStore.doctypes.filter(d => !d.is_child)" :key="dt.name" :value="dt.name">
            {{ dt.label }}
          </option>
        </select>
      </div>

      <!-- Link type (shortcut) -->
      <div v-if="isShortcut" class="space-y-1">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Тип посилання</label>
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
          {{ isClock ? 'Примітка' : 'Підзаголовок' }}
        </label>
        <input
          v-model="draft.description"
          class="w-full h-8 px-3 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
          @change="apply"
        />
      </div>

      <!-- Content (text widget) -->
      <div v-if="isText" class="space-y-1">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Вміст (HTML/текст)</label>
        <textarea
          v-model="draft.content"
          rows="5"
          class="w-full px-3 py-2 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none font-mono"
          @change="apply"
        />
      </div>

      <!-- Shortcuts grid: tile list editor -->
      <div v-if="isShortcutsGrid" class="space-y-2">
        <div class="flex items-center justify-between">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Плитки</label>
          <button
            class="flex items-center gap-1 text-xs text-primary hover:underline"
            @click="addTile"
          >
            <Plus class="size-3" /> Додати
          </button>
        </div>
        <div v-if="tiles.length === 0" class="py-3 text-center text-xs text-muted-foreground border rounded-md">
          Немає плиток — натисніть «Додати»
        </div>
        <div
          v-for="(tile, i) in tiles"
          :key="i"
          class="rounded-md border bg-muted/30 p-3 space-y-2"
        >
          <div class="flex items-center justify-between">
            <span class="text-xs font-medium text-muted-foreground">Плитка {{ i + 1 }}</span>
            <button class="text-muted-foreground hover:text-destructive transition-colors" @click="removeTile(i)">
              <Trash2 class="size-3.5" />
            </button>
          </div>
          <input
            :value="tile.title"
            class="w-full h-7 px-2.5 rounded border bg-background text-xs focus:outline-none focus:ring-2 focus:ring-primary/30"
            placeholder="Назва"
            @input="updateTile(i, 'title', ($event.target as HTMLInputElement).value)"
          />
          <div class="grid grid-cols-2 gap-1.5">
            <input
              :value="tile.icon"
              class="h-7 px-2.5 rounded border bg-background text-xs focus:outline-none focus:ring-2 focus:ring-primary/30"
              placeholder="Іконка (lucide)"
              @input="updateTile(i, 'icon', ($event.target as HTMLInputElement).value)"
            />
            <select
              :value="tile.link_type"
              class="h-7 px-2 rounded border bg-background text-xs focus:outline-none"
              @change="updateTile(i, 'link_type', ($event.target as HTMLSelectElement).value)"
            >
              <option value="DocType">DocType</option>
              <option value="Report">Звіт</option>
              <option value="Dashboard">Дашборд</option>
              <option value="URL">URL</option>
            </select>
          </div>
          <select
            v-if="tile.link_type === 'DocType'"
            :value="tile.link_to"
            class="w-full h-7 px-2 rounded border bg-background text-xs focus:outline-none focus:ring-2 focus:ring-primary/30"
            @change="updateTile(i, 'link_to', ($event.target as HTMLSelectElement).value)"
          >
            <option value="">— Виберіть —</option>
            <option v-for="dt in dtStore.doctypes.filter(d => !d.is_child)" :key="dt.name" :value="dt.name">{{ dt.label }}</option>
          </select>
          <input
            v-else
            :value="tile.link_to"
            class="w-full h-7 px-2.5 rounded border bg-background text-xs focus:outline-none focus:ring-2 focus:ring-primary/30"
            placeholder="URL або назва..."
            @input="updateTile(i, 'link_to', ($event.target as HTMLInputElement).value)"
          />
          <!-- Tile color -->
          <div class="flex gap-1.5">
            <button
              v-for="c in COLORS" :key="c.value"
              :title="c.label"
              :class="['w-5 h-5 rounded-full border-2 transition-transform hover:scale-110', tile.color === c.value ? 'border-foreground scale-110' : 'border-transparent']"
              :style="{ background: c.bg }"
              @click="updateTile(i, 'color', c.value)"
            />
          </div>
        </div>
      </div>

      <!-- Links editor -->
      <div v-if="isLinks" class="space-y-2">
        <div class="flex items-center justify-between">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Посилання</label>
          <button class="flex items-center gap-1 text-xs text-primary hover:underline" @click="addLink">
            <Plus class="size-3" /> Додати
          </button>
        </div>
        <div v-if="linkItems.length === 0" class="py-3 text-center text-xs text-muted-foreground border rounded-md">
          Немає посилань
        </div>
        <div v-for="(link, i) in linkItems" :key="i" class="rounded-md border bg-muted/30 p-3 space-y-2">
          <div class="flex items-center justify-between">
            <span class="text-xs font-medium text-muted-foreground">Посилання {{ i + 1 }}</span>
            <button class="text-muted-foreground hover:text-destructive transition-colors" @click="removeLink(i)">
              <Trash2 class="size-3.5" />
            </button>
          </div>
          <div class="grid grid-cols-2 gap-1.5">
            <input :value="link.icon" class="h-7 px-2.5 rounded border bg-background text-xs focus:outline-none" placeholder="Emoji 📋" @input="updateLink(i, 'icon', ($event.target as HTMLInputElement).value)" />
            <select :value="link.type" class="h-7 px-2 rounded border bg-background text-xs focus:outline-none" @change="updateLink(i, 'type', ($event.target as HTMLSelectElement).value)">
              <option value="DocType">DocType</option>
              <option value="Report">Звіт</option>
              <option value="Dashboard">Дашборд</option>
              <option value="URL">URL</option>
            </select>
          </div>
          <input :value="link.label" class="w-full h-7 px-2.5 rounded border bg-background text-xs focus:outline-none" placeholder="Назва" @input="updateLink(i, 'label', ($event.target as HTMLInputElement).value)" />
          <select
            v-if="link.type === 'DocType'"
            :value="link.link_to"
            class="w-full h-7 px-2 rounded border bg-background text-xs focus:outline-none focus:ring-2 focus:ring-primary/30"
            @change="updateLink(i, 'link_to', ($event.target as HTMLSelectElement).value)"
          >
            <option value="">— Виберіть —</option>
            <option v-for="dt in dtStore.doctypes.filter(d => !d.is_child)" :key="dt.name" :value="dt.name">{{ dt.label }}</option>
          </select>
          <input
            v-else
            :value="link.link_to"
            class="w-full h-7 px-2.5 rounded border bg-background text-xs focus:outline-none"
            placeholder="URL або назва..."
            @input="updateLink(i, 'link_to', ($event.target as HTMLInputElement).value)"
          />
          <input :value="link.description" class="w-full h-7 px-2.5 rounded border bg-background text-xs focus:outline-none" placeholder="Опис (опціонально)" @input="updateLink(i, 'description', ($event.target as HTMLInputElement).value)" />
        </div>
      </div>

      <!-- Aggregation (metric / table) -->
      <template v-if="isMetric || isTableWidget">
        <div class="space-y-1">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Агрегація</label>
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
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Поле</label>
          <input v-model="draft.field" class="w-full h-8 px-3 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" placeholder="fieldname" @change="apply" />
        </div>
      </template>

      <!-- Group by (donut / funnel / table) -->
      <div v-if="isDonut || isFunnel || isTableWidget" class="space-y-1">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Групувати за</label>
        <input v-model="draft.group_by" class="w-full h-8 px-3 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" placeholder="fieldname" @change="apply" />
      </div>

      <!-- Date field + period -->
      <template v-if="isChart || isMetric || isCalendar || isHeatmap || isFunnel || isTableWidget">
        <div class="space-y-1">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Поле дати</label>
          <input v-model="draft.date_field" class="w-full h-8 px-3 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" placeholder="created_at" @change="apply" />
        </div>
        <div class="space-y-1">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Період</label>
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
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Ширина</label>
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
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Колір</label>
        <div class="flex gap-2">
          <button
            v-for="c in COLORS" :key="c.value"
            :title="c.label"
            :class="['w-7 h-7 rounded-full border-2 transition-transform hover:scale-110', draft.color === c.value ? 'border-foreground scale-110' : 'border-transparent']"
            :style="{ background: c.bg }"
            @click="draft.color = c.value; apply()"
          />
        </div>
      </div>

      <!-- Icon -->
      <div v-if="isMetric || isShortcut" class="space-y-1">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Іконка (lucide)</label>
        <input v-model="draft.icon" class="w-full h-8 px-3 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" placeholder="BarChart2, Users..." @change="apply" />
      </div>

    </div>
  </div>
</template>
