<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DocType } from '@/types'
import type { SidebarMilestone } from '@/core/api/docs'
import { formatFull, formatSpan } from '@/core/datetime'
import { statusBadgeFor } from '@/core/status'
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

const props = defineProps<{
  doctype: DocType
  milestones: SidebarMilestone[]
}>()

const { t } = useI18n()

// One block per tracked field (usually just the status).
const groups = computed(() => {
  const byField = new Map<string, SidebarMilestone[]>()
  for (const m of props.milestones) {
    const list = byField.get(m.field) ?? []
    list.push(m)
    byField.set(m.field, list)
  }
  return [...byField.entries()].map(([field, rows]) => ({
    field,
    label: props.doctype.fields?.find((f) => f.fieldname === field)?.label ?? field,
    rows,
  }))
})

function badge(m: SidebarMilestone) {
  return statusBadgeFor(props.doctype, m.value) ?? { label: m.value || '—', class: '' }
}

function span(m: SidebarMilestone): string {
  if (m.duration_hours != null) return formatSpan(m.duration_hours * 3600)
  const since = m.entered_at ? Date.parse(m.entered_at) : NaN
  return Number.isNaN(since) ? '—' : formatSpan((Date.now() - since) / 1000)
}
</script>

<template>
  <div v-for="g in groups" :key="g.field" class="flex flex-col gap-2">
    <div class="text-xs font-medium text-muted-foreground">
      {{ groups.length > 1 ? t('Time in «{field}»', { field: g.label }) : t('Time in status') }}
    </div>
    <ol class="flex flex-col gap-1.5">
      <li v-for="m in g.rows" :key="m.name" class="flex items-center gap-2">
        <Badge variant="outline" :class="badge(m).class" class="max-w-40 truncate">
          {{ badge(m).label }}
        </Badge>
        <Tooltip>
          <TooltipTrigger as-child>
            <span class="ml-auto shrink-0 text-xs tabular-nums"
              :class="m.left_at ? 'text-muted-foreground' : 'font-medium'">
              <template v-if="m.approximate">≈ </template>{{ span(m) }}<template v-if="!m.left_at"> · {{ t('now') }}</template>
            </span>
          </TooltipTrigger>
          <TooltipContent>
            <div>{{ t('Entered') }}: {{ formatFull(m.entered_at) }}</div>
            <div v-if="m.left_at">{{ t('Left') }}: {{ formatFull(m.left_at) }}</div>
            <div v-if="m.approximate" class="text-muted-foreground">
              {{ t('Approximate: recorded when tracking started') }}
            </div>
          </TooltipContent>
        </Tooltip>
      </li>
    </ol>
  </div>
</template>
