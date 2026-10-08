<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DashboardWidget } from '@/types'
import { getAsyncWidgetComponent, getWidgetDef, widgetColSpan } from '@/core/widgetRegistry'

const props = defineProps<{
  widget: DashboardWidget
  data?: unknown
  loading?: boolean
  editMode?: boolean
  workspaceName?: string
}>()

const { t } = useI18n()

const emit = defineEmits<{
  edit: [widget: DashboardWidget]
  remove: [widget: DashboardWidget]
}>()

const widgetComponent = computed(() => getAsyncWidgetComponent(props.widget.widget_type))

const colSpanClass = computed(() => widgetColSpan(props.widget.cols))

// Each widget type declares its own height in manifest.json (apps' widgets too).
const minHeight = computed(() => getWidgetDef(props.widget.widget_type)?.minHeight ?? '220px')
</script>

<template>
  <div :style="{ minHeight }" :class="[colSpanClass,
    'group relative min-w-0 bg-card border rounded-lg shadow-sm overflow-hidden',
    editMode ? 'ring-2 ring-primary/20 cursor-grab active:cursor-grabbing' : '',
  ]">
    <!-- Edit overlay buttons -->
    <div v-if="editMode"
      class="absolute top-2 right-2 z-10 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity"
      @click.stop>
      <button
        class="p-1.5 rounded-md bg-card border hover:bg-muted transition-colors"
        :title="t('Configure')"
        @click="emit('edit', widget)">
        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/>
          <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/>
        </svg>
      </button>
      <button
        class="p-1.5 rounded-md bg-card border hover:bg-destructive hover:text-destructive-foreground transition-colors"
        :title="t('Delete')"
        @click="emit('remove', widget)">
        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/>
          <path d="M10 11v6m4-6v6"/><path d="M9 6V4h6v2"/>
        </svg>
      </button>
    </div>

    <!-- Widget render (drill-down clicks off while arranging the dashboard) -->
    <div :class="['h-full', editMode && 'pointer-events-none']">
      <component
        :is="widgetComponent"
        v-if="widgetComponent"
        :widget="widget"
        :data="data"
        :loading="loading"
        :workspace-name="workspaceName"
      />
    </div>
  </div>
</template>
