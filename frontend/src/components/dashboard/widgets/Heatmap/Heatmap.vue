<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import type { DashboardWidget } from '@/types'
import { formatIntl } from '@/core/datetime'
import { filteredListUrl } from '@/pages/reports/drilldown'

const { t } = useI18n()

const props = defineProps<{
  widget: DashboardWidget
  data: { entries: { date: string; count: number }[]; filters?: Record<string, unknown> } | null
  loading?: boolean
  workspaceName?: string
}>()

const router = useRouter()

interface Cell { date: Date; key: string; count: number; future: boolean }

const PERIOD_DAYS: Record<string, number> = { '7d': 7, '30d': 30, '90d': 90, '365d': 365 }
const DAY_LABELS = [t('Mon'), '', t('Wed'), '', t('Fri'), '', '']
// Literal class names so Tailwind generates them (no string-built `bg-primary/${n}`).
const LEVELS = ['bg-muted', 'bg-primary/25', 'bg-primary/50', 'bg-primary/75', 'bg-primary']

const periodDays = computed(() => PERIOD_DAYS[props.widget.period ?? '365d'] ?? 365)

/** Local YYYY-MM-DD — toISOString() would shift the day across the UTC boundary. */
function dayKey(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

const counts = computed(() => {
  const map = new Map<string, number>()
  for (const e of props.data?.entries ?? []) map.set(e.date.slice(0, 10), e.count)
  return map
})

// Week columns (Monday first) covering the widget's period up to today.
const weeks = computed(() => {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const cur = new Date(today)
  cur.setDate(cur.getDate() - (periodDays.value - 1))
  cur.setDate(cur.getDate() - ((cur.getDay() + 6) % 7))

  const out: Cell[][] = []
  while (cur <= today) {
    const week: Cell[] = []
    for (let d = 0; d < 7; d++) {
      const key = dayKey(cur)
      week.push({ date: new Date(cur), key, count: counts.value.get(key) ?? 0, future: cur > today })
      cur.setDate(cur.getDate() + 1)
    }
    out.push(week)
  }
  return out
})

// A month is labelled on the first week that contains its 1st day; a label
// closer than 3 weeks to the previous one would overlap it and is dropped.
const monthLabels = computed(() => {
  const labels: { col: number; label: string }[] = []
  weeks.value.forEach((week, wi) => {
    const first = wi === 0 ? week[0] : week.find(c => c.date.getDate() === 1)
    if (!first) return
    const prev = labels[labels.length - 1]
    if (prev && wi - prev.col < 3) {
      if (prev.col === 0) labels.pop()
      else return
    }
    labels.push({ col: wi, label: fmt(first.date, { month: 'short' }) })
  })
  return labels
})

const maxCount = computed(() => Math.max(1, ...(props.data?.entries ?? []).map(e => e.count)))
const totalCount = computed(() => (props.data?.entries ?? []).reduce((s, e) => s + e.count, 0))
const activeDays = computed(() => (props.data?.entries ?? []).filter(e => e.count > 0).length)
const busiest = computed(() => {
  const top = [...(props.data?.entries ?? [])].sort((a, b) => b.count - a.count)[0]
  return top?.count ? top : null
})

function level(count: number): string {
  if (!count) return LEVELS[0]
  return LEVELS[Math.min(4, Math.ceil((count / maxCount.value) * 4))]
}

/** Calendar-day formatting pinned to UTC, so the system timezone can't shift the day. */
function fmt(d: Date, opts: Intl.DateTimeFormatOptions): string {
  const utc = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()))
  return formatIntl(utc, { ...opts, timeZone: 'UTC' })
}

function fmtDay(d: Date | string): string {
  const date = typeof d === 'string' ? new Date(`${d.slice(0, 10)}T00:00:00`) : d
  return fmt(date, { day: 'numeric', month: 'long', year: 'numeric' })
}

/** Day cell → the widget's list filtered to that day. */
function open(cell: Cell) {
  const { widget, data } = props
  if (!cell.count || !widget.doctype || !widget.date_field || !data?.filters) return
  const next = new Date(cell.date)
  next.setDate(next.getDate() + 1)
  router.push(filteredListUrl(widget.doctype, {
    ...data.filters,
    [`${widget.date_field}__gte`]: cell.key,
    [`${widget.date_field}__lt`]: dayKey(next),
  }, props.workspaceName))
}
</script>

<template>
  <div class="flex flex-col h-full px-4 py-3">
    <div class="flex items-center justify-between mb-3 shrink-0">
      <p class="font-medium text-muted-foreground">{{ widget.title }}</p>
      <span v-if="!loading" class="text-muted-foreground">{{ t('{n} in {days} days').replace('{n}', String(totalCount)).replace('{days}', String(periodDays)) }}</span>
    </div>

    <div v-if="loading" class="flex-1 flex items-center">
      <div class="grid gap-[3px] w-full" style="grid-template-columns: repeat(53, 1fr)">
        <div v-for="i in 53 * 7" :key="i" class="aspect-square rounded-[2px] bg-muted animate-pulse" />
      </div>
    </div>

    <template v-else>
      <div class="flex-1 flex flex-col justify-center min-h-0">
        <div
          class="grid gap-[3px] items-center"
          :style="{ gridTemplateColumns: `auto repeat(${weeks.length}, minmax(0, 1fr))` }"
        >
          <!-- Month labels -->
          <div />
          <div
            v-for="m in monthLabels" :key="m.col"
            class="text-muted-foreground whitespace-nowrap leading-none pb-1 capitalize"
            :style="{ gridColumn: `${m.col + 2} / span 3`, gridRow: 1 }"
          >
            {{ m.label }}
          </div>

          <!-- Rows = weekdays, columns = weeks -->
          <template v-for="(dayLabel, d) in DAY_LABELS" :key="d">
            <div class="text-muted-foreground leading-none pr-1.5" :style="{ gridRow: d + 2 }">
              {{ dayLabel }}
            </div>
            <div
              v-for="(week, wi) in weeks" :key="week[d].key"
              :title="week[d].future ? undefined : `${fmtDay(week[d].date)}: ${week[d].count}`"
              :class="[
                'aspect-square rounded-[2px]',
                week[d].future ? 'invisible' : level(week[d].count),
                week[d].count ? 'cursor-pointer hover:ring-1 hover:ring-foreground/40' : '',
              ]"
              :style="{ gridRow: d + 2, gridColumn: wi + 2 }"
              @click="open(week[d])"
            />
          </template>
        </div>
      </div>

      <div class="flex items-center justify-between gap-3 mt-3 shrink-0 text-muted-foreground">
        <span class="truncate">
          {{ t('Active days:') }} <span class="text-foreground font-medium">{{ activeDays }}</span>
          <template v-if="busiest">
            · {{ t('busiest {day}').replace('{day}', fmtDay(busiest.date)) }}: <span class="text-foreground font-medium">{{ busiest.count }}</span>
          </template>
        </span>
        <div class="flex items-center gap-1 shrink-0">
          <span>{{ t('Few') }}</span>
          <div v-for="cls in LEVELS" :key="cls" :class="['size-2.5 rounded-[2px]', cls]" />
          <span>{{ t('Many') }}</span>
        </div>
      </div>
    </template>
  </div>
</template>
