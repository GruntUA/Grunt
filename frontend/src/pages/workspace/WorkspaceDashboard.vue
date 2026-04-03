<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { RefreshCw, LayoutDashboard, Pencil, Plus, Save, X, Calendar, Timer, Link2, Printer } from 'lucide-vue-next'
import draggable from 'vuedraggable'
import { docsApi } from '@/core/api/docs'
import { getDashboardData } from '@/core/api/dashboards'
import WidgetCard from '@/components/dashboard/WidgetCard.vue'
import WidgetConfigPanel from '@/components/dashboard/WidgetConfigPanel.vue'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type { DashboardWidget } from '@/types'
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

const dashboard = ref<DashboardDoc | null>(null)
const widgetData = ref<Record<string, unknown>>({})
const loading = ref(true)
const refreshing = ref(false)

const editMode = ref(false)
const saving = ref(false)
const configWidget = ref<DashboardWidget | null>(null)
const showConfigDialog = ref(false)

// Global date filter
const dateFrom = ref('')
const dateTo = ref('')

// Auto-refresh
const autoRefreshInterval = ref<number>(0) // 0 = off
const autoRefreshTimer = ref<ReturnType<typeof setInterval> | null>(null)

// Embed modal
const showEmbedModal = ref(false)

const embedUrl = computed(() => {
  const base = window.location.origin
  return `${base}/dashboard/${props.dashboardName}`
})

function startAutoRefresh(seconds: number) {
  stopAutoRefresh()
  if (seconds > 0) {
    autoRefreshTimer.value = setInterval(() => {
      refreshData()
    }, seconds * 1000)
  }
}

function stopAutoRefresh() {
  if (autoRefreshTimer.value) {
    clearInterval(autoRefreshTimer.value)
    autoRefreshTimer.value = null
  }
}

function onAutoRefreshChange() {
  startAutoRefresh(autoRefreshInterval.value)
}

onUnmounted(stopAutoRefresh)

async function refreshData() {
  if (!dashboard.value) return
  refreshing.value = true
  try {
    widgetData.value = await getDashboardData(props.dashboardName, {
      dateFrom: dateFrom.value || undefined,
      dateTo: dateTo.value || undefined,
    })
  } finally {
    refreshing.value = false }
}

async function load() {
  loading.value = true
  try {
    const doc = await docsApi.get('Dashboard', props.dashboardName) as unknown as DashboardDoc
    dashboard.value = { ...doc, widgets: doc.widgets ?? [] }
    widgetData.value = await getDashboardData(props.dashboardName, {
      dateFrom: dateFrom.value || undefined,
      dateTo: dateTo.value || undefined,
    })
  } catch (error: any) {
    if (error.response?.status === 404) {
      dashboard.value = null
    } else {
      console.error('Failed to load dashboard', error)
    }
  } finally {
    loading.value = false
  }
}

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
    const msg = (err as { response?: { data?: { detail?: string; error?: { message?: string } } } })
      ?.response?.data?.error?.message
      ?? (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      ?? 'Помилка створення дашборду'
    toast.error(msg)
  } finally {
    loading.value = false
  }
}

async function refresh() {
  if (!dashboard.value) return
  refreshing.value = true
  try {
    widgetData.value = await getDashboardData(props.dashboardName, {
      dateFrom: dateFrom.value || undefined,
      dateTo: dateTo.value || undefined,
    })
  } finally { refreshing.value = false }
}

function generateId() {
  return Math.random().toString(36).substring(2, 9)
}

function handleAddWidget() {
  const newWidget: DashboardWidget = {
    id: 'new-' + generateId(),
    widget_type: 'metric',
    title: 'Нова метрика',
    cols: 1,
    color: 'primary',
    doctype: '',
    aggregation: 'count',
    field: '',
    period: '30d',
    filters: undefined,
    group_by: '',
    date_field: '',
    sequence: dashboard.value?.widgets?.length || 0,
    icon: '',
    link_type: null,
    description: null,
    content: null,
  }
  configWidget.value = newWidget
  showConfigDialog.value = true
}

function handleEditWidget(widget: DashboardWidget) {
  configWidget.value = { ...widget }
  showConfigDialog.value = true
}

function handleRemoveWidget(widget: DashboardWidget) {
  if (!dashboard.value) return
  if (!confirm('Видалити віджет?')) return
  const idx = dashboard.value.widgets.findIndex(w => w.id === widget.id)
  if (idx !== -1) {
    dashboard.value.widgets.splice(idx, 1)
  }
}

function handleSaveWidgetConfig(widget: DashboardWidget) {
  if (!dashboard.value) return
  const idx = dashboard.value.widgets.findIndex(w => w.id === widget.id)
  if (idx !== -1) {
    dashboard.value.widgets[idx] = widget
  } else {
    dashboard.value.widgets.push(widget)
  }
  showConfigDialog.value = false
  refresh()
}

function handleConfigCancel() {
  showConfigDialog.value = false
  configWidget.value = null
}

async function saveDashboard() {
  if (!dashboard.value) return
  saving.value = true

  // Fix sequences based on array order
  dashboard.value.widgets.forEach((w, i) => {
    w.sequence = i
  })

  try {
    await docsApi.update('Dashboard', dashboard.value.name, {
      widgets: dashboard.value.widgets,
    })
    editMode.value = false
    await load()
  } catch (err: unknown) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message ?? 'Помилка збереження дашборду'
    toast.error(msg)
  } finally {
    saving.value = false
  }
}

function toggleEditMode() {
  if (editMode.value) {
    // Revert changes on cancel edit
    load()
    editMode.value = false
  } else {
    editMode.value = true
  }
}

function copyEmbedUrl() {
  navigator.clipboard.writeText(embedUrl.value)
  toast.success('Посилання скопійовано')
}

function printDashboard() {
  window.print()
}

onMounted(load)
</script>

<template>
  <div class="p-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-4">
      <div class="flex items-center gap-2">
        <LayoutDashboard class="w-5 h-5 text-muted-foreground" />
        <h1 class="text-lg font-semibold">{{ dashboard?.label ?? dashboardName }}</h1>
        <p v-if="dashboard?.description" class="text-sm text-muted-foreground ml-2">
          {{ dashboard.description }}
        </p>
      </div>

      <div class="flex items-center gap-2">
        <template v-if="editMode">
          <button
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-sm hover:bg-muted transition-colors"
            @click="handleAddWidget">
            <Plus class="w-4 h-4" />
            Додати
          </button>
          <button
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-sm hover:bg-muted transition-colors"
            @click="toggleEditMode">
            <X class="w-4 h-4" />
            Скасувати
          </button>
          <button
            class="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
            :class="{ 'opacity-50': saving }" :disabled="saving" @click="saveDashboard">
            <Save class="w-4 h-4" :class="{ 'animate-pulse': saving }" />
            Зберегти
          </button>
        </template>
        <template v-else>
          <!-- Global date filter -->
          <div v-if="dashboard" class="flex items-center gap-1.5">
            <Calendar class="w-4 h-4 text-muted-foreground shrink-0" />
            <input
              v-model="dateFrom"
              type="date"
              class="h-8 px-2 rounded-lg border bg-background text-xs focus:outline-none focus:ring-2 focus:ring-primary/30"
              @change="refreshData"
            />
            <span class="text-muted-foreground text-xs">—</span>
            <input
              v-model="dateTo"
              type="date"
              class="h-8 px-2 rounded-lg border bg-background text-xs focus:outline-none focus:ring-2 focus:ring-primary/30"
              @change="refreshData"
            />
          </div>

          <!-- Auto-refresh selector -->
          <div v-if="dashboard" class="flex items-center gap-1.5">
            <Timer class="w-4 h-4 text-muted-foreground shrink-0" />
            <select
              v-model.number="autoRefreshInterval"
              class="h-8 px-2 rounded-lg border bg-background text-xs focus:outline-none focus:ring-2 focus:ring-primary/30"
              @change="onAutoRefreshChange">
              <option :value="0">Авто</option>
              <option :value="30">30с</option>
              <option :value="60">1хв</option>
              <option :value="300">5хв</option>
              <option :value="600">10хв</option>
            </select>
          </div>

          <!-- Edit -->
          <button
            class="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-dashed border-primary/40 text-primary bg-primary/5 text-sm hover:bg-primary/10 transition-colors"
            @click="toggleEditMode">
            <Pencil class="w-4 h-4" />
            Налаштувати
          </button>

          <!-- Refresh -->
          <button class="flex items-center gap-2 px-3 py-1.5 rounded-lg border text-sm hover:bg-muted transition-colors"
            :class="{ 'opacity-50': refreshing || loading }" :disabled="refreshing || loading" @click="refresh">
            <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': refreshing }" />
            Оновити
          </button>

          <!-- Embed -->
          <button v-if="dashboard"
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-sm hover:bg-muted transition-colors"
            @click="showEmbedModal = true">
            <Link2 class="w-4 h-4" />
          </button>

          <!-- Print -->
          <button v-if="dashboard"
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-sm hover:bg-muted transition-colors"
            @click="printDashboard">
            <Printer class="w-4 h-4" />
          </button>
        </template>
      </div>
    </div>

    <!-- Skeleton -->
    <div v-if="loading" class="grid grid-cols-4 gap-4">
      <div v-for="i in 6" :key="i" class="h-36 bg-muted animate-pulse rounded-xl" />
    </div>

    <!-- Empty states -->
    <div v-else-if="!dashboard && !editMode"
      class="flex flex-col items-center justify-center py-24 text-muted-foreground">
      <LayoutDashboard class="w-12 h-12 mb-3 opacity-30" />
      <p class="text-sm mb-4">Дашборд для цього простору ще не створено</p>
      <button
        class="flex items-center gap-2 px-4 py-2 rounded-xl bg-primary/10 text-primary text-sm font-medium hover:bg-primary/20 transition-colors"
        @click="createDashboard">
        <Plus class="w-4 h-4" />
        Створити Дашборд
      </button>
    </div>

    <div v-else-if="dashboard?.widgets?.length === 0 && !editMode"
      class="flex flex-col items-center justify-center py-24 text-muted-foreground">
      <LayoutDashboard class="w-12 h-12 mb-3 opacity-30" />
      <p class="text-sm mb-4">Дашборд порожній</p>
      <button
        class="flex items-center gap-2 px-4 py-2 rounded-xl bg-primary/10 text-primary text-sm font-medium hover:bg-primary/20 transition-colors"
        @click="toggleEditMode">
        <Pencil class="w-4 h-4" />
        Налаштувати дашборд
      </button>
    </div>

    <!-- Dashboard area -->
    <div v-else>
      <div v-if="editMode && dashboard?.widgets.length === 0"
        class="flex flex-col items-center justify-center py-20 px-4 border-2 border-dashed border-primary/20 rounded-2xl bg-primary/5 mb-6 text-center">
        <div class="p-3 bg-background rounded-full shadow-sm mb-3">
          <Plus class="size-6 text-primary" />
        </div>
        <h3 class="text-lg font-bold text-primary mb-1">Почніть збирати свій дашборд</h3>
        <p class="text-sm text-muted-foreground mb-4 max-w-sm">Додавайте метрики, графіки та списки. Ви можете змінювати
          їх
          порядок простим перетягуванням.</p>
        <button
          class="flex items-center gap-2 px-4 py-2 rounded-xl bg-primary text-primary-foreground text-sm font-medium shadow-md hover:bg-primary/90 transition-colors hover:-translate-y-0.5"
          @click="handleAddWidget">
          <Plus class="w-4 h-4" />
          Додати віджет
        </button>
      </div>

      <!-- Widgets Grid / Drag & Drop -->
      <draggable v-if="dashboard?.widgets && dashboard.widgets.length > 0" v-model="dashboard.widgets" item-key="id"
        class="grid grid-cols-4 gap-4 auto-rows-auto" :disabled="!editMode" handle=".cursor-grab"
        ghost-class="opacity-50">
        <template #item="{ element }">
          <WidgetCard :widget="element" :data="(widgetData[element.id] as unknown)" :loading="refreshing"
            :workspace-name="workspaceName" :edit-mode="editMode" @edit="handleEditWidget"
            @remove="handleRemoveWidget" />
        </template>
      </draggable>
    </div>

    <!-- Widget Config Dialog -->
    <Dialog v-model:open="showConfigDialog">
      <DialogContent class="sm:max-w-[425px] p-0 gap-0 overflow-hidden bg-muted/5 border-border/50">
        <div class="h-[80vh] flex flex-col bg-background shadow-xl border rounded-[inherit]">
          <WidgetConfigPanel v-if="configWidget" :widget="configWidget" @save="handleSaveWidgetConfig"
            @cancel="handleConfigCancel" />
        </div>
      </DialogContent>
    </Dialog>

    <!-- Embed Dialog -->
    <Dialog v-model:open="showEmbedModal">
      <DialogContent class="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>Вбудувати дашборд</DialogTitle>
        </DialogHeader>
        <div class="space-y-4 pt-2">
          <div class="space-y-1.5">
            <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Пряме посилання</label>
            <div class="flex gap-2">
              <input
                :value="embedUrl"
                readonly
                class="flex-1 h-9 px-3 rounded-lg border bg-muted text-sm font-mono focus:outline-none"
              />
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
              readonly
              rows="3"
              class="w-full px-3 py-2 rounded-lg border bg-muted text-xs font-mono focus:outline-none resize-none"
            />
          </div>
        </div>
      </DialogContent>
    </Dialog>
  </div>
</template>
