<script setup lang="ts">
import { useRouter } from 'vue-router'
import type { Workspace } from '@/core/api/workspace'

const props = defineProps<{
  workspace: Workspace
  counts?: Record<string, number>
}>()

const router = useRouter()

function totalCount(): number {
  if (!props.counts) return 0
  return Object.values(props.counts).reduce((sum, v) => sum + v, 0)
}

function navigate() {
  router.push(`/${props.workspace.name}`)
}
</script>

<template>
  <div
    class="app-card relative bg-[--grunt-surface] border border-[--grunt-border] rounded-[--grunt-radius-lg] p-5 cursor-pointer flex flex-col transition-all duration-150 hover:-translate-y-0.5"
    :style="{
      '--card-color': workspace.color,
      borderLeftColor: workspace.color,
      borderLeftWidth: '4px',
      width: 'var(--grunt-app-card-w)',
      height: 'var(--grunt-app-card-h)',
    }"
    @click="navigate"
  >
    <span class="text-[32px] leading-none mb-2">{{ workspace.icon }}</span>
    <h3 class="text-base font-medium text-[--grunt-text-primary] mt-1">{{ workspace.label }}</h3>
    <p class="text-xs text-[--grunt-text-muted] mt-1 line-clamp-2 flex-1">{{ workspace.description }}</p>
    <div v-if="totalCount() > 0" class="mt-2">
      <span
        class="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full"
        :style="{ backgroundColor: workspace.color + '18', color: workspace.color }"
      >
        <span class="w-1.5 h-1.5 rounded-full" :style="{ backgroundColor: workspace.color }" />
        {{ totalCount() }} {{ totalCount() > 1 ? 'нових' : 'нове' }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.app-card:hover {
  border-left-color: var(--card-color) !important;
  box-shadow: var(--grunt-shadow-md);
}
</style>
