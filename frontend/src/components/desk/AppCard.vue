<script setup lang="ts">
import { useRouter } from 'vue-router'
import type { Workspace } from '@/core/api/workspace'
import { ArrowUpRight, Layers } from '@lucide/vue'
import AppIcon from '@/components/AppIcon.vue'

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
  router.push({ name: 'workspace-home', params: { workspaceName: props.workspace.name } })
}

// Generate a subtle gradient from the workspace color
function gradientStyle() {
  const c = props.workspace.color || '#6366f1'
  return {
    background: `linear-gradient(135deg, ${c}18 0%, ${c}08 60%, transparent 100%)`,
  }
}

function glowStyle() {
  const c = props.workspace.color || '#6366f1'
  return { boxShadow: `0 0 40px ${c}30, 0 0 0 1px ${c}20` }
}
</script>

<template>
  <div
    class="group relative overflow-hidden rounded-3xl border border-border/40 bg-card/70 backdrop-blur-sm cursor-pointer flex flex-col p-6 transition-all duration-500 hover:-translate-y-1.5 hover:border-transparent"
    :style="{ minWidth: '200px' }"
    @mouseenter="(e) => (e.currentTarget as HTMLElement).style.boxShadow = glowStyle().boxShadow"
    @mouseleave="(e) => (e.currentTarget as HTMLElement).style.boxShadow = ''"
    @click="navigate"
  >
    <!-- Gradient background tinted from workspace color -->
    <div
      class="absolute inset-0 opacity-80 transition-opacity duration-500 group-hover:opacity-100 pointer-events-none"
      :style="gradientStyle()"
    />

    <!-- Color accent bottom bar (animated) -->
    <div
      class="absolute bottom-0 left-6 right-6 h-[2px] rounded-full transition-all duration-500 scale-x-0 group-hover:scale-x-100 origin-left"
      :style="{ backgroundColor: workspace.color }"
    />

    <!-- Top-right arrow -->
    <ArrowUpRight
      class="absolute top-4 right-4 w-4 h-4 opacity-0 -translate-x-1 translate-y-1 group-hover:opacity-100 group-hover:translate-x-0 group-hover:translate-y-0 transition-all duration-300"
      :style="{ color: workspace.color }"
    />

    <!-- Icon -->
    <div class="relative mb-4">
      <div
        class="size-14 rounded-2xl flex items-center justify-center transition-transform duration-500 group-hover:scale-110 group-hover:rotate-3"
        :style="{ backgroundColor: workspace.color + '20', border: `1px solid ${workspace.color}30`, color: workspace.color }"
      >
        <AppIcon :icon="workspace.icon || 'package'" class="size-7" />
      </div>
    </div>

    <!-- Name & Description -->
    <div class="relative flex-1">
      <h3 class="text-base font-black text-foreground leading-tight mb-1.5 group-hover:text-primary transition-colors duration-300">
        {{ workspace.label }}
      </h3>
      <p class="text-xs text-muted-foreground/70 line-clamp-2 leading-relaxed">
        {{ workspace.description || 'Додаток Grunt' }}
      </p>
    </div>

    <!-- Count badge -->
    <div class="relative mt-4 flex items-center justify-between">
      <div v-if="totalCount() > 0" class="flex items-center gap-1.5">
        <div
          class="size-1.5 rounded-full animate-pulse"
          :style="{ backgroundColor: workspace.color }"
        />
        <span
          class="text-xs font-black tabular-nums"
          :style="{ color: workspace.color }"
        >{{ totalCount() }}</span>
        <span class="text-[10px] text-muted-foreground/50 font-medium">записів</span>
      </div>
      <div v-else class="flex items-center gap-1.5">
        <Layers class="size-3 text-muted-foreground/30" />
        <span class="text-[10px] text-muted-foreground/40 font-medium">Відкрити</span>
      </div>
    </div>
  </div>
</template>
