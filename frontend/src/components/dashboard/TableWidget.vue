<script setup lang="ts">
import { computed } from 'vue'
import type { DashboardWidget } from '@/types'

const props = defineProps<{
  widget: DashboardWidget
  data: { rows: { label: string; value: number }[]; aggregation?: string; field?: string | null } | null
  loading?: boolean
}>()

const rows = computed(() => props.data?.rows ?? [])
const maxValue = computed(() => Math.max(...rows.value.map(r => r.value), 1))

const aggLabel = computed(() => {
  const map: Record<string, string> = {
    count: 'Кількість', sum: 'Сума', avg: 'Середнє', min: 'Мін', max: 'Макс',
  }
  return map[props.data?.aggregation ?? 'count'] ?? 'Значення'
})

function barWidth(value: number): number {
  return Math.max(4, Math.round((value / maxValue.value) * 100))
}

function formatVal(v: number): string {
  return v % 1 === 0 ? String(v) : v.toFixed(1)
}
</script>

<template>
  <div class="flex flex-col h-full">
    <!-- Header -->
    <div class="px-4 pt-3 pb-2 shrink-0">
      <p class="font-medium text-muted-foreground">{{ widget.title }}</p>
    </div>

    <!-- Skeleton -->
    <div v-if="loading" class="flex-1 px-4 flex flex-col gap-1.5 py-1">
      <div v-for="i in 5" :key="i" class="h-6 bg-muted animate-pulse rounded" />
    </div>

    <!-- Empty -->
    <div v-else-if="rows.length === 0"
      class="flex-1 flex items-center justify-center text-muted-foreground">
      Немає даних
    </div>

    <!-- Table -->
    <div v-else class="flex-1 overflow-auto">
      <table class="w-full text-xs">
        <thead class="sticky top-0 bg-card border-b">
          <tr>
            <th class="px-4 py-2 text-left font-medium text-muted-foreground">
              {{ widget.group_by || 'Група' }}
            </th>
            <th class="px-4 py-2 text-right font-medium text-muted-foreground">
              {{ aggLabel }}
            </th>
          </tr>
        </thead>
        <tbody class="divide-y divide-border/40">
          <tr v-for="row in rows" :key="row.label"
            class="hover:bg-muted/30 transition-colors group">
            <td class="px-4 py-2">
              <div class="flex items-center gap-2">
                <!-- Bar -->
                <div class="flex-1 h-1.5 bg-muted/50 rounded-full overflow-hidden max-w-[80px]">
                  <div class="h-full bg-primary/60 rounded-full transition-all"
                    :style="{ width: barWidth(row.value) + '%' }" />
                </div>
                <span class="text-foreground/80 truncate max-w-[100px]">{{ row.label }}</span>
              </div>
            </td>
            <td class="px-4 py-2 text-right font-semibold tabular-nums text-foreground">
              {{ formatVal(row.value) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
