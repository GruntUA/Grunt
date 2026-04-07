<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useWorkspaceStore } from '@/stores/workspace'
import { workspaceApi } from '@/core/api/workspace'
import WidgetCard from '@/components/dashboard/WidgetCard.vue'

const props = defineProps<{ workspaceName: string }>()
const router = useRouter()
const wsStore = useWorkspaceStore()

const widgetData = ref<Record<string, unknown>>({})
const loading = ref(false)

const widgets = computed(() => {
  const ws = wsStore.active
  if (!ws) return []
  return (ws.widgets ?? []).slice().sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0))
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
  if (!wsStore.active || wsStore.active.name !== props.workspaceName) {
    await wsStore.setActive(props.workspaceName)
  }

  if (!hasWidgets.value) {
    // Fallback: redirect to first DocType list (legacy behavior)
    const firstDocType = wsStore.active?.items
      .slice()
      .sort((a, b) => a.sequence - b.sequence)
      .find(item => item.type === 'DocType' && item.link_to)

    if (firstDocType) {
      router.replace(`/${props.workspaceName}/list/${firstDocType.link_to}`)
      return
    }
  }

  await loadWidgetData()
}

onMounted(init)
watch(() => props.workspaceName, init)
</script>

<template>
  <div class="p-6">
    <!-- Header -->
    <div v-if="wsStore.active" class="flex items-center gap-3 mb-6">
      <span class="text-3xl">{{ wsStore.active.icon }}</span>
      <div>
        <h1 class="text-xl font-semibold text-foreground">{{ wsStore.active.label }}</h1>
        <p v-if="wsStore.active.description" class="text-sm text-muted-foreground">
          {{ wsStore.active.description }}
        </p>
      </div>
    </div>

    <!-- Widgets grid -->
    <div v-if="hasWidgets" class="grid grid-cols-4 gap-4">
      <WidgetCard
        v-for="widget in widgets"
        :key="widget.id"
        :widget="widget"
        :data="widgetData[widget.id]"
        :loading="loading"
        :workspace-name="workspaceName"
      />
    </div>

    <!-- Empty state (no widgets, no redirect target) -->
    <div v-else-if="wsStore.active" class="flex flex-col items-center justify-center py-20 text-center">
      <span class="text-5xl mb-4">{{ wsStore.active.icon }}</span>
      <p class="text-muted-foreground text-sm">Цей воркспейс ще не має модулів.</p>
      <p class="text-muted-foreground/60 text-xs mt-1">Додайте віджети у Studio → Воркспейси.</p>
    </div>
  </div>
</template>
