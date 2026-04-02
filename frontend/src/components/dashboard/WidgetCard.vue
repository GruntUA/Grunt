<script setup lang="ts">
import { computed } from 'vue'
import type { DashboardWidget } from '@/types'
import MetricWidget from './MetricWidget.vue'
import ChartWidget from './ChartWidget.vue'
import DonutWidget from './DonutWidget.vue'
import ListWidget from './ListWidget.vue'
import ShortcutWidget from './ShortcutWidget.vue'
import ShortcutsGridWidget from './ShortcutsGridWidget.vue'
import TextWidget from './TextWidget.vue'
import ClockWidget from './ClockWidget.vue'

const props = defineProps<{
  widget: DashboardWidget
  data?: unknown
  loading?: boolean
  editMode?: boolean
  workspaceName?: string
}>()

const emit = defineEmits<{
  edit: [widget: DashboardWidget]
  remove: [widget: DashboardWidget]
}>()

const colSpanClass = computed(() => ({
  1: 'col-span-1',
  2: 'col-span-2',
  3: 'col-span-3',
  4: 'col-span-4',
}[props.widget.cols] ?? 'col-span-1'))

const minH = computed(() => {
  if (props.widget.widget_type === 'metric') return 'min-h-[120px]'
  if (props.widget.widget_type === 'shortcut') return 'min-h-[120px]'
  if (props.widget.widget_type === 'clock') return 'min-h-[140px]'
  return 'min-h-[220px]'
})
</script>

<template>
  <div :class="[colSpanClass, minH,
    'group relative bg-card border rounded-xl shadow-sm overflow-hidden',
    editMode ? 'ring-2 ring-primary/20 cursor-grab active:cursor-grabbing' : '',
  ]">
    <!-- Edit overlay buttons -->
    <div v-if="editMode"
      class="absolute top-2 right-2 z-10 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity"
      @click.stop>
      <button
        class="p-1.5 rounded-md bg-card border hover:bg-muted transition-colors"
        title="Налаштувати"
        @click="emit('edit', widget)">
        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/>
          <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/>
        </svg>
      </button>
      <button
        class="p-1.5 rounded-md bg-card border hover:bg-destructive hover:text-destructive-foreground transition-colors"
        title="Видалити"
        @click="emit('remove', widget)">
        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/>
          <path d="M10 11v6m4-6v6"/><path d="M9 6V4h6v2"/>
        </svg>
      </button>
    </div>

    <!-- Widget renders -->
    <div class="h-full">
      <MetricWidget
        v-if="widget.widget_type === 'metric'"
        :widget="widget"
        :data="(data as { value: number; trend?: number | null })"
        :loading="loading"
      />
      <ChartWidget
        v-else-if="widget.widget_type === 'chart_area' || widget.widget_type === 'chart_bar'"
        :widget="widget"
        :data="(data as { labels: string[]; values: number[] })"
        :loading="loading"
      />
      <DonutWidget
        v-else-if="widget.widget_type === 'donut'"
        :widget="widget"
        :data="(data as { labels: string[]; values: number[] })"
        :loading="loading"
      />
      <ListWidget
        v-else-if="widget.widget_type === 'list'"
        :widget="widget"
        :data="(data as { items: Record<string, unknown>[]; title_field: string | null })"
        :loading="loading"
        :workspace-name="workspaceName"
      />
      <ShortcutWidget
        v-else-if="widget.widget_type === 'shortcut'"
        :widget="widget"
        :data="(data as { count: number } | null)"
        :loading="loading"
        :workspace-name="workspaceName"
      />
      <ShortcutsGridWidget
        v-else-if="widget.widget_type === 'shortcuts_grid'"
        :widget="widget"
        :workspace-name="workspaceName"
      />
      <TextWidget
        v-else-if="widget.widget_type === 'text'"
        :widget="widget"
      />
      <ClockWidget
        v-else-if="widget.widget_type === 'clock'"
        :widget="widget"
      />
    </div>
  </div>
</template>
