<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { Workspace } from '@/core/api/workspace'
import { ArrowUpRight, Layers } from '@lucide/vue'
import AppIcon from '@/components/AppIcon.vue'

const { t } = useI18n()

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
    class="group relative flex items-center gap-3 rounded-lg border bg-card p-3 transition-colors hover:border-primary/40"
    :style="{ borderLeftWidth: '3px', borderLeftColor: workspace.color || 'var(--primary)' }"
  >
    <!-- Icon -->
    <div
      class="flex size-9 shrink-0 items-center justify-center rounded-md"
      :style="{ backgroundColor: `color-mix(in srgb, ${workspace.color || 'var(--primary)'} 15%, transparent)`, color: workspace.color || 'var(--primary)' }"
    >
      <AppIcon :icon="workspace.icon || 'package'" class="size-4" />
    </div>

    <!-- Name & count -->
    <div class="min-w-0 flex-1">
      <h3 class="truncate font-semibold leading-tight text-foreground transition-colors group-hover:text-primary">
        {{ workspace.label }}
      </h3>
      <div v-if="totalCount() > 0" class="flex items-center gap-1 text-muted-foreground">
        <span class="font-medium tabular-nums" :style="{ color: workspace.color }">{{ totalCount() }}</span>
        <span>{{ t('records') }}</span>
      </div>
      <div v-else class="flex items-center gap-1 text-muted-foreground/60">
        <Layers class="size-3" />
        <span>{{ t('Open') }}</span>
      </div>
    </div>

    <!-- Hover arrow -->
    <ArrowUpRight class="size-4 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
  </router-link>
</template>
