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
    :title="workspace.description || workspace.label"
    class="group relative flex items-center gap-3 rounded-lg border border-border bg-card p-3 transition-colors hover:border-primary/40"
    :style="{ borderLeft: `3px solid ${workspace.color || 'var(--primary)'}` }"
  >
    <!-- Icon -->
    <div
      class="flex size-9 shrink-0 items-center justify-center rounded-md"
      :style="{ backgroundColor: workspace.color ? `color-mix(in srgb, ${workspace.color} 15%, transparent)` : 'var(--primary)', color: workspace.color || 'var(--primary)' }"
    >
      <AppIcon :icon="workspace.icon || 'package'" class="size-4" />
    </div>

    <!-- Name & count -->
    <div class="min-w-0 flex-1">
      <h3 class="truncate font-semibold text-foreground leading-tight group-hover:text-primary transition-colors">
        {{ workspace.label }}
      </h3>
      <div v-if="totalCount() > 0" class="flex items-center gap-1 text-muted-foreground/60">
        <span class="font-medium tabular-nums" :style="{ color: workspace.color }">{{ totalCount() }}</span>
        <span>записів</span>
      </div>
      <div v-else class="flex items-center gap-1 text-muted-foreground/40">
        <Layers class="size-3" />
        <span>Відкрити</span>
      </div>
    </div>

    <!-- Hover arrow -->
    <ArrowUpRight
      class="size-4 shrink-0 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity"
    />
  </router-link>
</template>
