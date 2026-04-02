<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { RefreshCw, LayoutDashboard, Pencil, Plus, Save, X } from 'lucide-vue-next'
import draggable from 'vuedraggable'
import { docsApi } from '@/core/api/docs'
import { getDashboardData } from '@/core/api/dashboards'
import WidgetCard from '@/components/dashboard/WidgetCard.vue'
import WidgetConfigPanel from '@/components/dashboard/WidgetConfigPanel.vue'
import {
  Dialog,
  DialogContent,
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

async function load() {
  loading.value = true
  try {
    const doc = await docsApi.get('Dashboard', props.dashboardName) as unknown as DashboardDoc
    dashboard.value = { ...doc, widgets: doc.widgets ?? [] }
    widgetData.value = await getDashboardData(props.dashboardName)
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
  try { widgetData.value = await getDashboardData(props.dashboardName) }
  finally { refreshing.value = false }
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
    filters: null,
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
  // Re-fetch data for the new/updated widget dynamically could be done here
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

onMounted(load)
</script>

<template>
  <div class="p-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
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
          <!-- Show edit button for admins or editors (assume always show for now) -->
          <button
            class="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-dashed border-primary/40 text-primary bg-primary/5 text-sm hover:bg-primary/10 transition-colors"
            @click="toggleEditMode">
            <Pencil class="w-4 h-4" />
            Налаштувати
          </button>
          <button class="flex items-center gap-2 px-3 py-1.5 rounded-lg border text-sm hover:bg-muted transition-colors"
            :class="{ 'opacity-50': refreshing || loading }" :disabled="refreshing || loading" @click="refresh">
            <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': refreshing }" />
            Оновити
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

    <!-- Config Dialog -->
    <Dialog v-model:open="showConfigDialog">
      <DialogContent class="sm:max-w-[425px] p-0 gap-0 overflow-hidden bg-muted/5 border-border/50">
        <div class="h-[80vh] flex flex-col bg-background shadow-xl border rounded-[inherit]">
          <WidgetConfigPanel v-if="configWidget" :widget="configWidget" @save="handleSaveWidgetConfig"
            @cancel="handleConfigCancel" />
        </div>
      </DialogContent>
    </Dialog>
  </div>
</template>
