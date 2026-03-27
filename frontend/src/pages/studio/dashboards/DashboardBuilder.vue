<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import draggable from 'vuedraggable'
import {
  ArrowLeft, Save, Plus, Eye, EyeOff, Settings2, LayoutDashboard,
} from 'lucide-vue-next'
import { dashboardApi } from '@/core/api/dashboards'
import WidgetCard from '@/components/dashboard/WidgetCard.vue'
import WidgetConfigPanel from '@/components/dashboard/WidgetConfigPanel.vue'
import type { Dashboard, DashboardWidget, WidgetType } from '@/types'
import { toast } from 'vue-sonner'

const props = defineProps<{ name: string }>()
const router = useRouter()

const dashboard = ref<Dashboard | null>(null)
const widgetData = ref<Record<string, unknown>>({})
const loading = ref(true)
const saving = ref(false)
const dataLoading = ref(false)
const selectedWidget = ref<DashboardWidget | null>(null)
const showConfig = ref(false)

async function load() {
  loading.value = true
  try {
    dashboard.value = await dashboardApi.get(props.name)
    await loadData()
  } finally { loading.value = false }
}

async function loadData() {
  if (!dashboard.value?.widgets.length) return
  dataLoading.value = true
  try { widgetData.value = await dashboardApi.getData(props.name) }
  catch { /* ignore data errors */ }
  finally { dataLoading.value = false }
}

onMounted(load)

function addWidget(type: WidgetType) {
  if (!dashboard.value) return
  const w: DashboardWidget = {
    id: crypto.randomUUID(),
    widget_type: type,
    title: { metric:'Нова метрика', chart_area:'Динаміка', chart_bar:'Стовпчиковий', donut:'Розподіл', list:'Останні записи' }[type],
    doctype: '',
    aggregation: 'count',
    period: '30d',
    cols: type === 'metric' ? 1 : type === 'list' ? 4 : 2,
    color: 'primary',
    sequence: dashboard.value.widgets.length,
    filters: {},
  }
  dashboard.value.widgets.push(w)
  selectedWidget.value = w
  showConfig.value = true
}

function editWidget(w: DashboardWidget) {
  selectedWidget.value = w
  showConfig.value = true
}

function removeWidget(w: DashboardWidget) {
  if (!dashboard.value) return
  dashboard.value.widgets = dashboard.value.widgets.filter(x => x.id !== w.id)
  if (selectedWidget.value?.id === w.id) { selectedWidget.value = null; showConfig.value = false }
}

function onWidgetSave(updated: DashboardWidget) {
  if (!dashboard.value) return
  const idx = dashboard.value.widgets.findIndex(w => w.id === updated.id)
  if (idx !== -1) dashboard.value.widgets[idx] = updated
  showConfig.value = false
  selectedWidget.value = null
}

async function save() {
  if (!dashboard.value) return
  saving.value = true
  try {
    const updated = await dashboardApi.update(props.name, {
      label: dashboard.value.label,
      description: dashboard.value.description,
      workspace: dashboard.value.workspace,
      roles: dashboard.value.roles,
      is_published: dashboard.value.is_published,
      widgets: dashboard.value.widgets.map((w, i) => ({ ...w, sequence: i })),
    })
    dashboard.value = updated
    await loadData()
    toast.success('Збережено')
  } catch { toast.error('Помилка збереження') }
  finally { saving.value = false }
}

function togglePublish() {
  if (dashboard.value) dashboard.value.is_published = !dashboard.value.is_published
}

const WIDGET_BUTTONS: { type: WidgetType; label: string; icon: string }[] = [
  { type: 'metric',     label: 'Метрика',  icon: '🔢' },
  { type: 'chart_bar',  label: 'Bar chart', icon: '📊' },
  { type: 'chart_area', label: 'Area chart', icon: '📈' },
  { type: 'donut',      label: 'Кругова',  icon: '🍩' },
  { type: 'list',       label: 'Список',   icon: '📋' },
]
</script>

<template>
  <div v-if="loading" class="flex items-center justify-center h-64">
    <div class="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" />
  </div>

  <div v-else-if="!dashboard" class="p-8 text-muted-foreground">Дашборд не знайдено</div>

  <div v-else class="flex h-screen flex-col overflow-hidden">
    <!-- Top bar -->
    <div class="flex items-center justify-between px-6 h-14 border-b bg-card shrink-0 gap-4">
      <div class="flex items-center gap-3">
        <button class="p-2 rounded-lg hover:bg-muted transition-colors" @click="router.back()">
          <ArrowLeft class="w-4 h-4" />
        </button>
        <LayoutDashboard class="w-4 h-4 text-muted-foreground" />
        <input
          v-model="dashboard.label"
          class="font-semibold text-sm bg-transparent focus:outline-none focus:ring-0 border-b border-transparent focus:border-border"
        />
      </div>

      <div class="flex items-center gap-2">
        <!-- Publish toggle -->
        <button
          :class="['flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors',
            dashboard.is_published ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'hover:bg-muted']"
          @click="togglePublish">
          <component :is="dashboard.is_published ? Eye : EyeOff" class="w-3.5 h-3.5" />
          {{ dashboard.is_published ? 'Опублікований' : 'Чернетка' }}
        </button>

        <!-- Workspace -->
        <input
          v-model="dashboard.workspace"
          class="h-8 px-3 rounded-lg border bg-background text-xs focus:outline-none focus:ring-2 focus:ring-primary/30 w-36"
          placeholder="Воркспейс"
        />

        <button
          class="flex items-center gap-2 px-4 py-1.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
          :disabled="saving"
          @click="save">
          <Save class="w-4 h-4" />
          {{ saving ? 'Збереження…' : 'Зберегти' }}
        </button>
      </div>
    </div>

    <!-- Body: palette | canvas | config -->
    <div class="flex flex-1 min-h-0">

      <!-- Left: widget palette -->
      <div class="w-44 border-r bg-card shrink-0 flex flex-col overflow-y-auto">
        <p class="px-4 pt-4 pb-2 text-xs font-medium text-muted-foreground uppercase tracking-wide">Додати</p>
        <div class="px-2 space-y-1 pb-4">
          <button
            v-for="btn in WIDGET_BUTTONS" :key="btn.type"
            class="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm hover:bg-muted transition-colors text-left"
            @click="addWidget(btn.type)">
            <span>{{ btn.icon }}</span>
            <span class="text-xs">{{ btn.label }}</span>
          </button>
        </div>
      </div>

      <!-- Center: canvas -->
      <div class="flex-1 overflow-auto bg-muted/30 p-6">
        <div v-if="!dashboard.widgets.length"
          class="flex flex-col items-center justify-center h-64 text-muted-foreground gap-2">
          <LayoutDashboard class="w-10 h-10 opacity-30" />
          <p class="text-sm">Додайте перший віджет з палітри ліворуч</p>
        </div>

        <draggable
          v-else
          v-model="dashboard.widgets"
          item-key="id"
          class="grid grid-cols-4 gap-4 auto-rows-auto"
          handle=".drag-handle"
          :animation="200"
        >
          <template #item="{ element: w }">
            <WidgetCard
              :widget="w"
              :data="(widgetData[w.id] as unknown)"
              :loading="dataLoading"
              :edit-mode="true"
              class="drag-handle"
              @edit="editWidget"
              @remove="removeWidget"
            />
          </template>
        </draggable>
      </div>

      <!-- Right: config panel -->
      <div v-if="showConfig" class="w-72 border-l bg-card shrink-0 flex flex-col overflow-hidden">
        <WidgetConfigPanel
          :widget="selectedWidget"
          @save="onWidgetSave"
          @cancel="showConfig = false"
        />
      </div>
    </div>
  </div>
</template>
