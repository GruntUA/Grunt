<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { RefreshCw, LayoutDashboard } from 'lucide-vue-next'
import { docsApi } from '@/core/api/docs'
import { getDashboardData } from '@/core/api/dashboards'
import WidgetCard from '@/components/dashboard/WidgetCard.vue'
import type { DashboardWidget } from '@/types'

const props = defineProps<{
  workspaceName: string
  dashboardName: string
}>()

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

async function load() {
  loading.value = true
  try {
    const r = await docsApi.get('Dashboard', props.dashboardName)
    dashboard.value = r.data as DashboardDoc
    widgetData.value = await getDashboardData(props.dashboardName)
  } finally { loading.value = false }
}

async function refresh() {
  refreshing.value = true
  try { widgetData.value = await getDashboardData(props.dashboardName) }
  finally { refreshing.value = false }
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

      <button
        class="flex items-center gap-2 px-3 py-1.5 rounded-lg border text-sm hover:bg-muted transition-colors"
        :class="{ 'opacity-50': refreshing }"
        @click="refresh">
        <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': refreshing }" />
        Оновити
      </button>
    </div>

    <!-- Skeleton -->
    <div v-if="loading" class="grid grid-cols-4 gap-4">
      <div v-for="i in 6" :key="i" class="h-36 bg-muted animate-pulse rounded-xl" />
    </div>

    <!-- Empty -->
    <div v-else-if="!dashboard?.widgets?.length"
      class="flex flex-col items-center justify-center py-24 text-muted-foreground">
      <LayoutDashboard class="w-12 h-12 mb-3 opacity-30" />
      <p class="text-sm">Дашборд порожній</p>
    </div>

    <!-- Widgets grid -->
    <div v-else class="grid grid-cols-4 gap-4 auto-rows-auto">
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
</template>
