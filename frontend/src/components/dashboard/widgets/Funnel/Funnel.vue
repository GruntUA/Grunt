<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import type { DashboardWidget } from '@/types'
import { filteredListUrl, groupFilter } from '@/pages/reports/drilldown'

const { t } = useI18n()

const props = defineProps<{
  widget: DashboardWidget
  data: { stages: Stage[]; filters?: Record<string, unknown> } | null
  loading?: boolean
  workspaceName?: string
}>()

interface Stage { label: string; key?: unknown; count: number }

const router = useRouter()

const stages = computed(() => props.data?.stages ?? [])
const maxCount = computed(() => Math.max(...stages.value.map(s => s.count), 1))

const COLOR_MAP: Record<string, string> = {
  primary: '#2D6A4F', blue: '#3b82f6', amber: '#f59e0b',
  red: '#ef4444', violet: '#8b5cf6', cyan: '#06b6d4',
}

const color = computed(() => COLOR_MAP[props.widget.color] ?? COLOR_MAP.primary)

const canOpen = computed(() => !!props.widget.doctype && !!props.widget.group_by && !!props.data?.filters)

/** Stage → the widget's list filtered to that group. */
function open(stage: Stage) {
  const { widget, data } = props
  if (!canOpen.value || !stage.count) return
  router.push(filteredListUrl(
    widget.doctype, { ...data!.filters, ...groupFilter(widget.group_by!, stage.key) }, props.workspaceName,
  ))
}

function widthPct(count: number): number {
  return Math.max(20, Math.round((count / maxCount.value) * 100))
}
</script>

<template>
  <div class="flex flex-col h-full px-4 py-3">
    <!-- Header -->
    <p class="font-medium text-muted-foreground mb-3 shrink-0">{{ widget.title }}</p>

    <!-- Skeleton -->
    <div v-if="loading" class="flex-1 flex flex-col justify-center gap-2">
      <div v-for="i in 4" :key="i" class="h-7 bg-muted animate-pulse rounded-md" :style="{ width: (100 - i * 10) + '%', margin: '0 auto' }" />
    </div>

    <!-- Empty -->
    <div v-else-if="stages.length === 0"
      class="flex-1 flex items-center justify-center text-muted-foreground">
      {{ t('No data') }}
    </div>

    <!-- Funnel -->
    <div v-else class="flex-1 flex flex-col justify-center gap-1.5">
      <div v-for="(stage, i) in stages" :key="stage.label"
        class="flex items-center gap-2 mx-auto w-full"
        :style="{ maxWidth: widthPct(stage.count) + '%' }">
        <div
          :class="['flex items-center justify-between w-full px-3 py-1.5 rounded-md text-white font-medium transition-all',
            canOpen && stage.count && 'cursor-pointer hover:brightness-110']"
          :style="{ backgroundColor: color, opacity: 1 - i * (0.12) }"
          @click="open(stage)">
          <span class="truncate">{{ stage.label }}</span>
          <span class="ml-2 tabular-nums font-semibold shrink-0">{{ stage.count }}</span>
        </div>
      </div>

      <!-- Conversion hint -->
      <div v-if="stages.length >= 2" class="text-center text-muted-foreground mt-1">
        {{ t('Conversion:') }} {{ stages[0].count > 0 ? Math.round(stages[stages.length - 1].count / stages[0].count * 100) : 0 }}%
      </div>
    </div>
  </div>
</template>
