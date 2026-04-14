<script setup lang="ts">
import { useRouter } from 'vue-router'
import type { Workspace } from '@/core/api/workspace'
import { ArrowUpRight } from '@lucide/vue'

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
    class="group relative w-44 h-44 bg-card border border-border/60 rounded-xl p-5 cursor-pointer flex flex-col transition-all duration-200 hover:-translate-y-1 hover:shadow-lg hover:shadow-black/[0.06] hover:border-border"
    @click="navigate"
  >
    <!-- Color accent line -->
    <div
      class="absolute left-0 top-3 bottom-3 w-[3px] rounded-full transition-all duration-200 group-hover:top-2 group-hover:bottom-2"
      :style="{ backgroundColor: workspace.color }"
    />

    <!-- Arrow indicator on hover -->
    <ArrowUpRight class="absolute top-3.5 right-3.5 w-4 h-4 text-muted-foreground/40 opacity-0 group-hover:opacity-100 transition-opacity duration-200" />

    <span class="text-[28px] leading-none mb-2">{{ workspace.icon }}</span>
    <h3 class="text-[15px] font-semibold text-foreground mt-1 leading-tight">{{ workspace.label }}</h3>
    <p class="text-xs text-muted-foreground mt-1 line-clamp-2 flex-1">{{ workspace.description }}</p>

    <div v-if="totalCount() > 0" class="mt-auto pt-2">
      <span
        class="inline-flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded-full"
        :style="{ backgroundColor: workspace.color + '14', color: workspace.color }"
      >
        <span class="w-1.5 h-1.5 rounded-full" :style="{ backgroundColor: workspace.color }" />
        {{ totalCount() }}
      </span>
    </div>
  </div>
</template>
