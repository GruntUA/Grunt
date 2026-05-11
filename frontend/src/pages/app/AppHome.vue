<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useAppStore } from '@/stores/app'
import { useSidebarStore } from '@/stores/sidebar'
import { docsApi } from '@/core/api/docs'
import { getPageData } from '@/core/api/pages'
import AppIcon from '@/components/AppIcon.vue'
import WidgetCard from '@/components/dashboard/WidgetCard.vue'
import { PanelLeft } from '@lucide/vue'
import type { DashboardWidget } from '@/types'

const props = defineProps<{ workspaceName: string }>()
const appStore = useAppStore()
const sidebarStore = useSidebarStore()

const widgets = ref<DashboardWidget[]>([])
const widgetData = ref<Record<string, unknown>>({})
const loading = ref(false)

const homePage = computed(() => appStore.active?.home_page ?? null)
const hasWidgets = computed(() => widgets.value.length > 0)

async function loadPage(pageName: string) {
  loading.value = true
  try {
    const doc = await docsApi.get('Page', pageName) as { widgets?: DashboardWidget[] }
    const raw = doc.widgets ?? []
    widgets.value = [...raw].sort((a, b) => (a.sequence || 0) - (b.sequence || 0))
    widgetData.value = await getPageData(pageName)
  } catch {
    widgets.value = []
    widgetData.value = {}
  } finally {
    loading.value = false
  }
}

async function init() {
  if (!appStore.active || appStore.active.name !== props.workspaceName) {
    await appStore.setActive(props.workspaceName)
  }
  widgets.value = []
  widgetData.value = {}
  if (homePage.value) {
    await loadPage(homePage.value)
  }
}

onMounted(init)
watch(() => props.workspaceName, init)
</script>

<template>
  <div class="flex flex-1 flex-col gap-4 p-4 md:p-5 animate-in fade-in duration-500">
    <!-- Header -->
    <div v-if="appStore.active" class="flex items-center gap-3 mb-6">
      <button
        class="md:hidden size-8 flex items-center justify-center rounded-lg text-muted-foreground/80 hover:text-foreground hover:bg-muted/50 transition-colors shrink-0 -ml-3"
        @click="sidebarStore.toggleMobile"
      >
        <PanelLeft class="size-4" />
      </button>
      <AppIcon :icon="appStore.active.icon || 'folder'" class="size-8 shrink-0" />
      <div>
        <h1 class="text-xl font-semibold text-foreground">{{ appStore.active.label }}</h1>
        <p v-if="appStore.active.description" class="text-sm text-muted-foreground">
          {{ appStore.active.description }}
        </p>
      </div>
    </div>

    <!-- Loading skeleton -->
    <div v-if="loading" class="grid grid-cols-4 gap-4">
      <div v-for="i in 4" :key="i" class="h-32 bg-muted animate-pulse rounded-xl" />
    </div>

    <!-- Widgets grid -->
    <div v-else-if="hasWidgets" class="grid grid-cols-4 gap-4">
      <WidgetCard
        v-for="widget in widgets"
        :key="widget.id"
        :widget="widget"
        :data="(widgetData[widget.id] ?? null) as unknown"
        :loading="loading"
        :workspace-name="workspaceName"
      />
    </div>

    <!-- Empty state -->
    <div v-else-if="appStore.active" class="flex flex-col items-center justify-center py-20 text-center">
      <AppIcon :icon="appStore.active.icon || 'folder'" class="size-12 mb-4 text-muted-foreground/40" />
      <p class="text-muted-foreground text-sm">Домашня сторінка не налаштована.</p>
      <p class="text-muted-foreground/60 text-xs mt-1">
        Створіть <router-link :to="`/${workspaceName}/Page`" class="text-primary hover:underline">Сторінку</router-link>
        і вкажіть її у полі «Домашня сторінка» в налаштуваннях AppMenu.
      </p>
    </div>
  </div>
</template>
