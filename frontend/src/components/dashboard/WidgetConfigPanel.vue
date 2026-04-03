<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import type { DashboardWidget, WidgetType, WidgetAggregation, WidgetPeriod, WidgetCols } from '@/types'
import { useDocTypeStore } from '@/stores/doctype'

const props = defineProps<{ widget: DashboardWidget | null }>()
const emit = defineEmits<{ save: [widget: DashboardWidget]; cancel: [] }>()

const dtStore = useDocTypeStore()
dtStore.loadAll()

const draft = ref<DashboardWidget | null>(null)

watch(() => props.widget, (w) => {
  draft.value = w ? { ...w } : null
}, { immediate: true })

function save() {
  if (draft.value) emit('save', draft.value)
}

const WIDGET_TYPES: { value: WidgetType; label: string; icon: string }[] = [
  { value: 'metric',     label: 'Метрика',      icon: '🔢' },
  { value: 'chart_area', label: 'Графік (Area)', icon: '📈' },
  { value: 'chart_bar',  label: 'Графік (Bar)',  icon: '📊' },
  { value: 'donut',      label: 'Кругова',       icon: '🍩' },
  { value: 'list',       label: 'Список',        icon: '📋' },
  { value: 'shortcut',       label: 'Ярлик',         icon: '🔗' },
  { value: 'shortcuts_grid', label: 'Сітка ярликів', icon: '⊞' },
  { value: 'text',           label: 'Текст',         icon: '📝' },
  { value: 'clock',          label: 'Годинник',      icon: '🕐' },
  { value: 'activity',       label: 'Активність',    icon: '🕒' },
  { value: 'calendar',       label: 'Календар',      icon: '📅' },
  { value: 'heatmap',        label: 'Теплокарта',    icon: '🟩' },
  { value: 'funnel',         label: 'Воронка',       icon: '🔽' },
  { value: 'table',          label: 'Таблиця',       icon: '📊' },
]

const AGGREGATIONS: { value: WidgetAggregation; label: string }[] = [
  { value: 'count', label: 'Кількість (COUNT)' },
  { value: 'sum',   label: 'Сума (SUM)' },
  { value: 'avg',   label: 'Середнє (AVG)' },
  { value: 'min',   label: 'Мінімум' },
  { value: 'max',   label: 'Максимум' },
]

const PERIODS: { value: WidgetPeriod; label: string }[] = [
  { value: '7d',  label: '7 днів' },
  { value: '30d', label: '30 днів' },
  { value: '90d', label: '3 місяці' },
  { value: '365d', label: 'Рік' },
]

const COLS: { value: WidgetCols; label: string }[] = [
  { value: 1, label: '1/4 ширини' },
  { value: 2, label: '1/2 ширини' },
  { value: 3, label: '3/4 ширини' },
  { value: 4, label: 'Повна ширина' },
]

const COLORS = [
  { value: 'primary', label: 'Зелений' },
  { value: 'blue',    label: 'Синій' },
  { value: 'amber',   label: 'Жовтий' },
  { value: 'red',     label: 'Червоний' },
  { value: 'violet',  label: 'Фіолетовий' },
  { value: 'cyan',    label: 'Блакитний' },
]

const needsField = computed(() => {
  if (!draft.value) return false
  return ['sum', 'avg', 'min', 'max'].includes(draft.value.aggregation)
})

const isChart = computed(() =>
  draft.value?.widget_type === 'chart_area' || draft.value?.widget_type === 'chart_bar'
)
const isDonut = computed(() => draft.value?.widget_type === 'donut')
const isList = computed(() => draft.value?.widget_type === 'list')
const isMetric = computed(() => draft.value?.widget_type === 'metric')
const isShortcut      = computed(() => draft.value?.widget_type === 'shortcut')
const isShortcutsGrid = computed(() => draft.value?.widget_type === 'shortcuts_grid')
const isText          = computed(() => draft.value?.widget_type === 'text')
const isClock         = computed(() => draft.value?.widget_type === 'clock')
const isActivity      = computed(() => draft.value?.widget_type === 'activity')
const isCalendar      = computed(() => draft.value?.widget_type === 'calendar')
const isHeatmap       = computed(() => draft.value?.widget_type === 'heatmap')
const isFunnel        = computed(() => draft.value?.widget_type === 'funnel')
const isTableWidget   = computed(() => draft.value?.widget_type === 'table')
const isDataWidget    = computed(() => isMetric.value || isChart.value || isDonut.value || isList.value || isCalendar.value || isHeatmap.value || isFunnel.value || isTableWidget.value)
</script>

<template>
  <div v-if="!draft" class="flex items-center justify-center h-full text-muted-foreground text-sm p-6">
    Виберіть віджет для налаштування
  </div>

  <div v-else class="flex flex-col h-full overflow-hidden">
    <div class="px-5 py-4 border-b">
      <h3 class="font-semibold text-sm">Налаштування віджета</h3>
    </div>

    <div class="flex-1 overflow-y-auto p-5 space-y-5">
      <!-- Widget type -->
      <div class="space-y-1.5">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Тип</label>
        <div class="grid grid-cols-2 gap-1.5">
          <button
            v-for="t in WIDGET_TYPES" :key="t.value"
            :class="[
              'flex items-center gap-2 px-3 py-2 rounded-lg border text-sm transition-colors',
              draft.widget_type === t.value
                ? 'bg-primary text-primary-foreground border-primary'
                : 'hover:bg-muted border-border',
            ]"
            @click="draft.widget_type = t.value"
          >
            <span>{{ t.icon }}</span>
            <span class="text-xs">{{ t.label }}</span>
          </button>
        </div>
      </div>

      <!-- Title -->
      <div class="space-y-1.5">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Назва</label>
        <input v-model="draft.title" class="w-full h-9 px-3 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" placeholder="Назва віджета" />
      </div>

      <!-- DocType / Link target -->
      <div v-if="isDataWidget || isShortcut" class="space-y-1.5">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          {{ isShortcut ? 'Ціль' : 'DocType' }}
        </label>
        <select v-if="isDataWidget" v-model="draft.doctype" class="w-full h-9 px-3 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30">
          <option value="">— Виберіть —</option>
          <option v-for="dt in dtStore.doctypes.filter(d => !d.is_child)" :key="dt.name" :value="dt.name">
            {{ dt.label }}
          </option>
        </select>
        <input v-else v-model="draft.doctype" class="w-full h-9 px-3 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" placeholder="Назва DocType, Report, Dashboard або URL" />
      </div>

      <!-- DocType filter (activity widget — optional) -->
      <div v-if="isActivity" class="space-y-1.5">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Фільтр за DocType <span class="normal-case font-normal">(опціонально)</span></label>
        <select v-model="draft.doctype" class="w-full h-9 px-3 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30">
          <option value="">— Всі DocType —</option>
          <option v-for="dt in dtStore.doctypes.filter(d => !d.is_child)" :key="dt.name" :value="dt.name">
            {{ dt.label }}
          </option>
        </select>
      </div>

      <!-- Link type (shortcut only) -->
      <div v-if="isShortcut" class="space-y-1.5">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Тип посилання</label>
        <select v-model="draft.link_type" class="w-full h-9 px-3 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30">
          <option value="DocType">DocType (список)</option>
          <option value="Report">Звіт</option>
          <option value="Dashboard">Дашборд</option>
          <option value="URL">Зовнішній URL</option>
        </select>
      </div>

      <!-- Description / subtitle -->
      <div v-if="isShortcut || isClock" class="space-y-1.5">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          {{ isClock ? 'Місце / Примітка' : 'Опис (підзаголовок)' }}
        </label>
        <input v-model="draft.description" class="w-full h-9 px-3 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" placeholder="Текст підзаголовку..." />
      </div>

      <!-- Content (text widget) -->
      <div v-if="isText" class="space-y-1.5">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Вміст (HTML або текст)</label>
        <textarea v-model="draft.content" rows="6"
          class="w-full px-3 py-2 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none font-mono" />
      </div>

      <!-- Content (shortcuts_grid — JSON tiles) -->
      <div v-if="isShortcutsGrid" class="space-y-1.5">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Плитки (JSON)</label>
        <textarea v-model="draft.content" rows="8"
          class="w-full px-3 py-2 rounded-lg border bg-background text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none"
          placeholder='[{"title":"Назва","icon":"Users","link_type":"DocType","link_to":"User","color":"blue"}]' />
        <p class="text-[11px] text-muted-foreground">JSON масив: title, icon, link_type (DocType/Report/Dashboard/URL), link_to, color</p>
      </div>

      <!-- Aggregation (metric only) -->
      <template v-if="isMetric">
        <div class="space-y-1.5">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Агрегація</label>
          <select v-model="draft.aggregation" class="w-full h-9 px-3 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30">
            <option v-for="a in AGGREGATIONS" :key="a.value" :value="a.value">{{ a.label }}</option>
          </select>
        </div>
        <div v-if="needsField" class="space-y-1.5">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Поле для розрахунку</label>
          <input v-model="draft.field" class="w-full h-9 px-3 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" placeholder="fieldname" />
        </div>
      </template>

      <!-- Group by (donut / funnel / table) -->
      <div v-if="isDonut || isFunnel || isTableWidget" class="space-y-1.5">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Групувати за</label>
        <input v-model="draft.group_by" class="w-full h-9 px-3 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" placeholder="fieldname" />
      </div>

      <!-- Aggregation for table widget -->
      <template v-if="isTableWidget">
        <div class="space-y-1.5">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Агрегація</label>
          <select v-model="draft.aggregation" class="w-full h-9 px-3 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30">
            <option v-for="a in AGGREGATIONS" :key="a.value" :value="a.value">{{ a.label }}</option>
          </select>
        </div>
        <div v-if="needsField" class="space-y-1.5">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Поле для розрахунку</label>
          <input v-model="draft.field" class="w-full h-9 px-3 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" placeholder="fieldname" />
        </div>
      </template>

      <!-- Date field + period (chart / metric / calendar / heatmap / funnel / table) -->
      <template v-if="isChart || isMetric || isCalendar || isHeatmap || isFunnel || isTableWidget">
        <div class="space-y-1.5">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Поле дати</label>
          <input v-model="draft.date_field" class="w-full h-9 px-3 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" placeholder="created_at" />
        </div>
        <div class="space-y-1.5">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Період</label>
          <select v-model="draft.period" class="w-full h-9 px-3 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30">
            <option v-for="p in PERIODS" :key="p.value" :value="p.value">{{ p.label }}</option>
          </select>
        </div>
      </template>

      <!-- Width -->
      <div class="space-y-1.5">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Ширина</label>
        <div class="grid grid-cols-4 gap-1">
          <button
            v-for="c in COLS" :key="c.value"
            :class="[
              'py-1.5 rounded-md border text-xs transition-colors',
              draft.cols === c.value ? 'bg-primary text-primary-foreground border-primary' : 'hover:bg-muted',
            ]"
            @click="draft.cols = c.value"
          >{{ c.value }}/4</button>
        </div>
      </div>

      <!-- Color -->
      <div class="space-y-1.5">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Колір</label>
        <div class="flex gap-2 flex-wrap">
          <button
            v-for="c in COLORS" :key="c.value"
            :title="c.label"
            :class="[
              'w-7 h-7 rounded-full border-2 transition-transform hover:scale-110',
              draft.color === c.value ? 'border-foreground scale-110' : 'border-transparent',
            ]"
            :style="{ background: { primary:'#2D6A4F', blue:'#3b82f6', amber:'#f59e0b', red:'#ef4444', violet:'#8b5cf6', cyan:'#06b6d4' }[c.value] }"
            @click="draft.color = c.value"
          />
        </div>
      </div>

      <!-- Icon (metric) -->
      <div v-if="isMetric || isShortcut" class="space-y-1.5">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Іконка (lucide)</label>
        <input v-model="draft.icon" class="w-full h-9 px-3 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" placeholder="BarChart2, Users, FileText …" />
      </div>
    </div>

    <!-- Actions -->
    <div class="px-5 py-4 border-t flex gap-2">
      <button
        class="flex-1 h-9 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
        @click="save">
        Зберегти
      </button>
      <button
        class="h-9 px-4 rounded-lg border text-sm hover:bg-muted transition-colors"
        @click="emit('cancel')">
        Скасувати
      </button>
    </div>
  </div>
</template>
