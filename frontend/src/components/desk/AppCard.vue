<script setup lang="ts">
import type { Workspace } from '@/core/api/workspace'
import { ArrowUpRight, Layers } from '@lucide/vue'
import AppIcon from '@/components/AppIcon.vue'

const props = defineProps<{
  workspace: Workspace
  counts?: Record<string, number>
}>()

function totalCount(): number {
  if (!props.counts) return 0
  return Object.values(props.counts).reduce((sum, v) => sum + v, 0)
}
</script>

<template>
  <router-link
    :to="{ name: 'workspace-home', params: { workspaceName: workspace.name } }"
    class="group relative overflow-hidden rounded-lg border border-border bg-card cursor-pointer flex flex-col p-6 transition-colors hover:border-primary/40"
    :style="{ minWidth: '200px', borderLeft: `3px solid ${workspace.color || 'var(--primary)'}` }"
  >
    <!-- Top-right arrow -->
    <ArrowUpRight
      class="absolute top-4 right-4 size-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity"
    />

    <!-- Icon -->
    <div class="mb-4">
      <div
        class="size-14 rounded-lg flex items-center justify-center"
        :style="{ backgroundColor: workspace.color ? `color-mix(in srgb, ${workspace.color} 15%, transparent)` : 'var(--primary)', color: workspace.color || 'var(--primary)' }"
      >
        <AppIcon :icon="workspace.icon || 'package'" class="size-7" />
      </div>
    </div>

    <!-- Name & Description -->
    <div class="flex-1">
      <h3 class="text-base font-semibold text-foreground leading-tight mb-1.5 group-hover:text-primary transition-colors">
        {{ workspace.label }}
      </h3>
      <p class="text-xs text-muted-foreground/70 line-clamp-2 leading-relaxed">
        {{ workspace.description || 'Додаток Grunt' }}
      </p>
    </div>

    <!-- Count badge -->
    <div class="mt-4 flex items-center justify-between">
      <div v-if="totalCount() > 0" class="flex items-center gap-1.5">
        <span class="text-xs font-semibold tabular-nums" :style="{ color: workspace.color }">{{ totalCount() }}</span>
        <span class="text-xs text-muted-foreground/50 font-medium">записів</span>
      </div>
      <div v-else class="flex items-center gap-1.5">
        <Layers class="size-3 text-muted-foreground/30" />
        <span class="text-xs text-muted-foreground/40 font-medium">Відкрити</span>
      </div>
    </div>
  </router-link>
</template>
