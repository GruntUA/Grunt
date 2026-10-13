<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DashboardWidget } from '@/types'
import { getAsyncWidgetComponent, getWidgetDef, widgetColSpan } from '@/core/widgetRegistry'
import { Pencil, Trash2 } from '@lucide/vue'
import { Button } from '@/components/ui/button'

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
const minHeight = computed(() => getWidgetDef(props.widget.widget_type)?.minHeight ?? '220px')</script>

<template>
  <div :style="{ minHeight }" :class="[colSpanClass,
    'group relative min-w-0 bg-card border rounded-lg shadow-sm overflow-hidden',    editMode ? 'ring-2 ring-primary/20 cursor-grab active:cursor-grabbing' : '',
  ]">
    <!-- Edit overlay buttons -->
    <div v-if="editMode"
      class="absolute top-2 right-2 z-10 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity"
      @click.stop>
      <Button variant="outline" size="icon-xs" :title="t('Configure')" :aria-label="t('Configure')" @click="emit('edit', widget)">
        <Pencil />
      </Button>
      <Button variant="outline" size="icon-xs" class="hover:text-destructive" :title="t('Delete')" :aria-label="t('Delete')" @click="emit('remove', widget)">
        <Trash2 />
      </Button>
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
