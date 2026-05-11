<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useAppStore } from '@/stores/app'
import { useSidebarStore } from '@/stores/sidebar'
import { workspaceApi } from '@/core/api/workspace'
import AppIcon from '@/components/AppIcon.vue'
import WidgetCard from '@/components/dashboard/WidgetCard.vue'
import { PanelLeft } from '@lucide/vue'

const props = defineProps<{ workspaceName: string }>()
const appStore = useAppStore()
const sidebarStore = useSidebarStore()

const widgetData = ref<Record<string, unknown>>({})
const loading = ref(false)

const widgets = computed(() => {
  const raw = appStore.active ? appStore.active.widgets : []
  let items: any[] = []
  if (Array.isArray(raw)) {
    items = raw
  } else if (typeof raw === 'string') {
    try {
      items = JSON.parse(raw) || []
    } catch {
      items = []
    }
  }

  return [...items].sort((a, b) => (a.sequence || 0) - (b.sequence || 0))
})

const hasWidgets = computed(() => widgets.value.length > 0)

async function loadWidgetData() {
  if (!hasWidgets.value) return
  loading.value = true
  try {
    widgetData.value = await workspaceApi.getWidgetData(props.workspaceName)
  } catch {
    widgetData.value = {}
  } finally {
    loading.value = false
  }
}

async function init() {
  if (!appStore.active || appStore.active.name !== props.workspaceName) {
    await appStore.setActive(props.workspaceName)
  }

  await loadWidgetData()
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

    <!-- Widgets grid -->
    <div v-if="hasWidgets" class="grid grid-cols-4 gap-4">
      <WidgetCard v-for="widget in widgets" :key="widget.id" :widget="widget" :data="widgetData[widget.id]"
        :loading="loading" :workspace-name="workspaceName" />
    </div>

    <!-- Empty state (no widgets, no redirect target) -->
    <div v-else-if="appStore.active" class="flex flex-col items-center justify-center py-20 text-center">
      <AppIcon :icon="appStore.active.icon || 'folder'" class="size-12 mb-4 text-muted-foreground/40" />
      <p class="text-muted-foreground text-sm">Цей воркспейс ще не має модулів.</p>
      <p class="text-muted-foreground/60 text-xs mt-1">
        Додайте віджети у
        <router-link :to="`/${workspaceName}/studio/workspaces`" class="text-primary hover:underline">Studio →
          Воркспейси</router-link>.
      </p>
    </div>
  </div>
</template>
