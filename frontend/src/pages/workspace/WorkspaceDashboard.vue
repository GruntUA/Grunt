<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import AppIcon from '@/components/AppIcon.vue'
import {
  RefreshCw, LayoutDashboard, Pencil, Plus, Save, X,
  Calendar, Timer, Link2, Printer, GripVertical,
} from '@lucide/vue'
import draggable from 'vuedraggable'
import { docsApi } from '@/core/api/docs'
import { getDashboardData } from '@/core/api/dashboards'
import WidgetCard from '@/components/dashboard/WidgetCard.vue'
import WidgetConfigPanel from '@/components/dashboard/WidgetConfigPanel.vue'
import type { DashboardWidget, WidgetType } from '@/types'
import { useToast } from '@/core/composables/useToast'

const props = defineProps<{
  workspaceName: string
  dashboardName: string
}>()

const toast = useToast()

interface DashboardDoc {
  id: string
  name: string
  label: string
  description?: string
  is_published: boolean
  widgets: DashboardWidget[]
}

// ── State ─────────────────────────────────────────────────────────────────────

const dashboard   = ref<DashboardDoc | null>(null)
const widgetData  = ref<Record<string, unknown>>({})
const loading     = ref(true)
const refreshing  = ref(false)
const editMode    = ref(false)
const saving      = ref(false)

const selectedWidgetId = ref<string | null>(null)

const selectedWidget = computed<DashboardWidget | null>(() =>
  dashboard.value?.widgets.find(w => w.id === selectedWidgetId.value) ?? null
)

// Global date filter
const dateFrom = ref('')
const dateTo   = ref('')

// Auto-refresh
const autoRefreshInterval = ref<number>(0)
const autoRefreshTimer    = ref<ReturnType<typeof setInterval> | null>(null)

// Embed modal
const showEmbedModal = ref(false)
const embedUrl = computed(() => `${window.location.origin}/dashboard/${props.dashboardName}`)

// ── Widget types palette ───────────────────────────────────────────────────────

const WIDGET_TYPES: { value: WidgetType; label: string; icon: string }[] = [
  { value: 'metric',         label: 'Метрика',       icon: '🔢' },
  { value: 'gauge',          label: 'Gauge',         icon: '🎯' },
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
]

// ── Data loading ───────────────────────────────────────────────────────────────

async function loadData() {
  try {
    widgetData.value = await getDashboardData(props.dashboardName, {
      dateFrom: dateFrom.value || undefined,
      dateTo:   dateTo.value   || undefined,
    })
  } catch { /* silent */ }
}

async function load() {
  loading.value = true
  try {
    const doc = await docsApi.get('Dashboard', props.dashboardName) as unknown as DashboardDoc
    dashboard.value = { ...doc, widgets: doc.widgets ?? [] }
    await loadData()
  } catch (error: unknown) {
    if ((error as { response?: { status?: number } })?.response?.status === 404) {
      dashboard.value = null
    }
  } finally {
    loading.value = false
  }
}

async function refresh() {
  if (!dashboard.value) return
  refreshing.value = true
  try { await loadData() } finally { refreshing.value = false }
}

// ── Auto-refresh ───────────────────────────────────────────────────────────────

function startAutoRefresh(seconds: number) {
  stopAutoRefresh()
  if (seconds > 0) autoRefreshTimer.value = setInterval(refresh, seconds * 1000)
}
function stopAutoRefresh() {
  if (autoRefreshTimer.value) { clearInterval(autoRefreshTimer.value); autoRefreshTimer.value = null }
}
onUnmounted(stopAutoRefresh)

// ── Dashboard CRUD ─────────────────────────────────────────────────────────────

async function createDashboard() {
  loading.value = true
  try {
    await docsApi.create('Dashboard', {
      name: props.dashboardName,
      label: props.dashboardName,
      is_published: true,
      workspace: props.workspaceName,
      widgets: [],
    })
    await load()
  } catch (err: unknown) {
    const msg = (err as { response?: { data?: { error?: { message?: string }; detail?: string } } })
      ?.response?.data?.error?.message
      ?? (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      ?? 'Помилка створення дашборду'
    toast.error(msg)
  } finally {
    loading.value = false
  }
}

async function saveDashboard() {
  if (!dashboard.value) return
  saving.value = true
  dashboard.value.widgets.forEach((w, i) => { w.sequence = i })
  try {
    await docsApi.update('Dashboard', dashboard.value.name, { widgets: dashboard.value.widgets })
    exitEdit()
    await load()
  } catch (err: unknown) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message ?? 'Помилка збереження'
    toast.error(msg)
  } finally {
    saving.value = false
  }
}

// ── Edit mode ──────────────────────────────────────────────────────────────────

function enterEdit() {
  editMode.value = true
  selectedWidgetId.value = null
}

function exitEdit() {
  editMode.value = false
  selectedWidgetId.value = null
}

function cancelEdit() {
  exitEdit()
  load()
}

// ── Widget management ──────────────────────────────────────────────────────────

function generateId() { return 'w-' + Math.random().toString(36).substring(2, 9) }

function addWidget(type: WidgetType) {
  if (!dashboard.value) return
  const id = generateId()
  const newWidget: DashboardWidget = {
    id,
    widget_type: type,
    title: WIDGET_TYPES.find(t => t.value === type)?.label ?? 'Новий',
    cols: type === 'shortcut' || type === 'clock' ? 1 : type === 'gauge' ? 1 : 2,
    color: 'primary',
    doctype: '',
    aggregation: 'count',
    field: '',
    period: '30d',
    filters: undefined,
    group_by: '',
    date_field: '',
    sequence: dashboard.value.widgets.length,
    icon: '',
    link_type: null,
    description: null,
    min_value: type === 'gauge' ? 0 : undefined,
    max_value: type === 'gauge' ? 100 : undefined,
    content: type === 'shortcuts_grid' ? '[]' : null,
  }
  dashboard.value.widgets.push(newWidget)
  selectedWidgetId.value = id
}

function selectWidget(widget: DashboardWidget) {
  selectedWidgetId.value = widget.id
}

function removeWidget(widget: DashboardWidget) {
  if (!dashboard.value) return
  const idx = dashboard.value.widgets.findIndex(w => w.id === widget.id)
  if (idx !== -1) dashboard.value.widgets.splice(idx, 1)
  if (selectedWidgetId.value === widget.id) selectedWidgetId.value = null
}

function handleWidgetChange(updated: DashboardWidget) {
  if (!dashboard.value) return
  const idx = dashboard.value.widgets.findIndex(w => w.id === updated.id)
  if (idx !== -1) dashboard.value.widgets[idx] = updated
}

function handleRemoveFromPanel() {
  const w = selectedWidget.value
  if (w) removeWidget(w)
}

// ── Embed ──────────────────────────────────────────────────────────────────────

function copyEmbedUrl() {
  navigator.clipboard.writeText(embedUrl.value)
  toast.success('Посилання скопійовано')
}

onMounted(load)

const printPage = () => window.print()
</script>

<template>
<div>
  <!-- ── Normal view ────────────────────────────────────────────────────────── -->
  <div class="p-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-4">
      <div class="flex items-center gap-2">
        <LayoutDashboard class="w-5 h-5 text-muted-foreground" />
        <h1 class="text-lg font-semibold">{{ dashboard?.label ?? dashboardName }}</h1>
        <p v-if="dashboard?.description" class="text-sm text-muted-foreground ml-2">{{ dashboard.description }}</p>
      </div>

      <div class="flex items-center gap-2">
        <!-- Date filter -->
        <div v-if="dashboard && !editMode" class="flex items-center gap-1.5">
          <Calendar class="w-4 h-4 text-muted-foreground shrink-0" />
          <input v-model="dateFrom" type="date"
            class="h-8 px-2 rounded-lg border bg-background text-xs focus:outline-none focus:ring-2 focus:ring-primary/30"
            @change="refresh" />
          <span class="text-muted-foreground text-xs">—</span>
          <input v-model="dateTo" type="date"
            class="h-8 px-2 rounded-lg border bg-background text-xs focus:outline-none focus:ring-2 focus:ring-primary/30"
            @change="refresh" />
        </div>

        <!-- Auto-refresh -->
        <div v-if="dashboard && !editMode" class="flex items-center gap-1.5">
          <Timer class="w-4 h-4 text-muted-foreground shrink-0" />
          <select v-model.number="autoRefreshInterval"
            class="h-8 px-2 rounded-lg border bg-background text-xs focus:outline-none focus:ring-2 focus:ring-primary/30"
            @change="startAutoRefresh(autoRefreshInterval)">
            <option :value="0">Авто</option>
            <option :value="30">30с</option>
            <option :value="60">1хв</option>
            <option :value="300">5хв</option>
            <option :value="600">10хв</option>
          </select>
        </div>

        <template v-if="!editMode">
          <button
            class="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-dashed border-primary/40 text-primary bg-primary/5 text-sm hover:bg-primary/10 transition-colors"
            @click="enterEdit">
            <Pencil class="w-4 h-4" /> Налаштувати
          </button>
          <button
            class="flex items-center gap-2 px-3 py-1.5 rounded-lg border text-sm hover:bg-muted transition-colors"
            :disabled="refreshing || loading"
            @click="refresh">
            <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': refreshing }" /> Оновити
          </button>
          <button v-if="dashboard"
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-sm hover:bg-muted transition-colors"
            @click="showEmbedModal = true">
            <Link2 class="w-4 h-4" />
          </button>
          <button v-if="dashboard"
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-sm hover:bg-muted transition-colors"
            @click="printPage">
            <Printer class="w-4 h-4" />
          </button>
        </template>
      </div>
    </div>

    <!-- Skeleton -->
    <div v-if="loading" class="grid grid-cols-4 gap-4">
      <div v-for="i in 6" :key="i" class="h-36 bg-muted animate-pulse rounded-xl" />
    </div>

    <!-- Empty: no dashboard -->
    <div v-else-if="!dashboard"
      class="flex flex-col items-center justify-center py-24 text-muted-foreground">
      <LayoutDashboard class="w-12 h-12 mb-3 opacity-30" />
      <p class="text-sm mb-4">Дашборд ще не створено</p>
      <button
        class="flex items-center gap-2 px-4 py-2 rounded-xl bg-primary/10 text-primary text-sm font-medium hover:bg-primary/20 transition-colors"
        @click="createDashboard">
        <Plus class="w-4 h-4" /> Створити Дашборд
      </button>
    </div>

    <!-- Empty: no widgets -->
    <div v-else-if="!editMode && dashboard.widgets.length === 0"
      class="flex flex-col items-center justify-center py-24 text-muted-foreground">
      <LayoutDashboard class="w-12 h-12 mb-3 opacity-30" />
      <p class="text-sm mb-4">Дашборд порожній</p>
      <button
        class="flex items-center gap-2 px-4 py-2 rounded-xl bg-primary/10 text-primary text-sm font-medium hover:bg-primary/20 transition-colors"
        @click="enterEdit">
        <Pencil class="w-4 h-4" /> Налаштувати
      </button>
    </div>

    <!-- Widgets grid (normal mode) -->
    <div v-else-if="!editMode && dashboard.widgets.length > 0"
      class="grid grid-cols-4 gap-4 auto-rows-auto">
      <WidgetCard
        v-for="w in dashboard.widgets"
        :key="w.id"
        :widget="w"
        :data="(widgetData[w.id] as unknown)"
        :loading="refreshing"
        :workspace-name="workspaceName"
      />
    </div>
  </div>

  <!-- ── Edit mode overlay ──────────────────────────────────────────────────── -->
  <Teleport to="body">
    <div v-if="editMode" class="fixed inset-0 z-50 flex flex-col bg-background overflow-hidden">

      <!-- Edit header -->
      <div class="flex items-center gap-3 px-4 py-2.5 border-b border-border bg-card shrink-0">
        <LayoutDashboard class="size-4 text-muted-foreground" />
        <span class="text-sm font-semibold">{{ dashboard?.label ?? dashboardName }}</span>
        <span class="text-xs font-medium bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-400 px-2 py-0.5 rounded">
          Режим редагування
        </span>
        <div class="ml-auto flex items-center gap-2">
          <button
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-sm hover:bg-muted transition-colors"
            @click="cancelEdit">
            <X class="w-4 h-4" /> Скасувати
          </button>
          <button
            class="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
            :class="{ 'opacity-50': saving }"
            :disabled="saving"
            @click="saveDashboard">
            <Save class="w-4 h-4" :class="{ 'animate-pulse': saving }" /> Зберегти
          </button>
        </div>
      </div>

      <!-- 3-column body -->
      <div class="flex flex-1 overflow-hidden">

        <!-- ── Left: widget palette ──────────────────────────────────────────── -->
        <div class="w-52 shrink-0 border-r border-border bg-muted/20 overflow-y-auto">
          <div class="px-3 py-3">
            <p class="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground mb-2 px-1">
              Типи віджетів
            </p>
            <div class="space-y-0.5">
              <button
                v-for="t in WIDGET_TYPES"
                :key="t.value"
                class="w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-sm text-left hover:bg-background hover:shadow-sm transition-all border border-transparent hover:border-border"
                @click="addWidget(t.value)"
              >
                <AppIcon :icon="t.icon" class="size-4 shrink-0 text-muted-foreground" />
                <span class="text-sm">{{ t.label }}</span>
                <Plus class="size-3 ml-auto text-muted-foreground opacity-0 group-hover:opacity-100" />
              </button>
            </div>
          </div>
        </div>

        <!-- ── Center: canvas ─────────────────────────────────────────────────── -->
        <div
          class="flex-1 overflow-y-auto bg-muted/10 p-4"
          @click.self="selectedWidgetId = null"
        >
          <!-- Empty canvas hint -->
          <div v-if="dashboard && dashboard.widgets.length === 0"
            class="flex flex-col items-center justify-center py-20 border-2 border-dashed border-primary/20 rounded-2xl bg-primary/5 text-center">
            <div class="text-4xl mb-3">👈</div>
            <h3 class="text-base font-semibold text-primary mb-1">Оберіть тип віджета</h3>
            <p class="text-sm text-muted-foreground max-w-xs">Натисніть на будь-який тип у лівій панелі — він з'явиться тут</p>
          </div>

          <draggable
            v-else-if="dashboard"
            v-model="dashboard.widgets"
            item-key="id"
            class="grid grid-cols-4 gap-3 auto-rows-auto"
            handle=".drag-handle"
            ghost-class="opacity-40"
          >
            <template #item="{ element }">
              <div
                :class="[
                  'relative rounded-xl border-2 transition-all cursor-pointer group',
                  selectedWidgetId === element.id
                    ? 'border-primary shadow-md'
                    : 'border-transparent hover:border-primary/30',
                ]"
                @click.stop="selectWidget(element)"
              >
                <!-- Drag handle -->
                <div class="absolute top-1.5 left-1.5 z-10 drag-handle cursor-grab opacity-0 group-hover:opacity-60 transition-opacity p-0.5 rounded bg-background/80">
                  <GripVertical class="size-3.5 text-muted-foreground" />
                </div>
                <!-- Remove button -->
                <button
                  class="absolute top-1.5 right-1.5 z-10 p-1 rounded bg-background/80 border opacity-0 group-hover:opacity-100 transition-opacity hover:bg-destructive hover:text-destructive-foreground hover:border-destructive"
                  @click.stop="removeWidget(element)"
                >
                  <X class="size-3" />
                </button>
                <!-- Widget preview -->
                <WidgetCard
                  :widget="element"
                  :data="(widgetData[element.id] as unknown)"
                  :workspace-name="workspaceName"
                />
              </div>
            </template>
          </draggable>
        </div>

        <!-- ── Right: config panel ────────────────────────────────────────────── -->
        <div class="w-72 shrink-0 border-l border-border bg-card overflow-hidden flex flex-col">
          <WidgetConfigPanel
            :widget="selectedWidget"
            @change="handleWidgetChange"
            @remove="handleRemoveFromPanel"
          />
        </div>

      </div>
    </div>
  </Teleport>

  <!-- ── Embed dialog ───────────────────────────────────────────────────────── -->
  <Dialog v-model:visible="showEmbedModal" header="Вбудувати дашборд" modal
    :pt="{ root: { class: 'sm:max-w-[500px]' }, content: { class: 'p-0 px-6 pb-6 pt-2' } }">
    <div class="space-y-4">
        <div class="space-y-1.5">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Пряме посилання</label>
          <div class="flex gap-2">
            <input :value="embedUrl" readonly
              class="flex-1 h-9 px-3 rounded-lg border bg-muted text-sm font-mono focus:outline-none" />
            <button
              class="px-3 h-9 rounded-lg border text-sm hover:bg-muted transition-colors"
              @click="copyEmbedUrl">
              Копіювати
            </button>
          </div>
        </div>
        <div class="space-y-1.5">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">iframe</label>
          <textarea
            :value="`<iframe src=&quot;${embedUrl}&quot; width=&quot;100%&quot; height=&quot;600&quot; frameborder=&quot;0&quot;></iframe>`"
            readonly rows="3"
            class="w-full px-3 py-2 rounded-lg border bg-muted text-xs font-mono focus:outline-none resize-none"
          />
        </div>
      </div>
  </Dialog>
</div>
</template>
