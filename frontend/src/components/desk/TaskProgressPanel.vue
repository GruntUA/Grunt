<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref, computed, onMounted, watch } from 'vue'
import { useElementSize } from '@vueuse/core'
import { useQueryClient } from '@tanstack/vue-query'
import { CircleCheck, CircleAlert, CircleX, ChevronDown, ChevronUp, X } from '@lucide/vue'
import { useTaskTracker, type TaskEntry } from '@/core/composables/useTaskTracker'
import { toast } from '@/core/composables/useToast'
import { useDialog } from '@/core/composables/useDialog'
import { formatFileSize } from '@/core/fileUtils'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Spinner } from '@/components/ui/spinner'

const { t } = useI18n()

const tracker = useTaskTracker()
const queryClient = useQueryClient()
const collapsed = ref(false)

const visible = computed(() => tracker.count.value > 0)

const panel = ref<HTMLElement | null>(null)
const { height } = useElementSize(panel, undefined, { box: 'border-box' })
watch(height, (h) => { tracker.panelHeight.value = panel.value ? h : 0 })

onMounted(() => {
  if (localStorage.getItem('grunt_token')) void tracker.restore()
})

// A finished task refreshes its DocType's list; a failed one also leaves a toast.
const reported = new Set<string>()
watch(tracker.tasks, (tasks) => {
  for (const task of tasks) {
    if (task.status === 'active' || reported.has(task.id)) continue
    reported.add(task.id)
    if (task.doctype) void queryClient.invalidateQueries({ queryKey: ['documents', task.doctype] })
    if (task.status === 'error') toast.error(`${task.title}: ${task.description ?? t('Failed')}`)
  }
})

async function cancel(task: TaskEntry) {
  const title = task.title
  const message = t('Stop «{title}»? What is done so far is discarded.', { title }).replace('{title}', title)
  if (await useDialog().confirm(message, t('Cancel task'))) {
    await tracker.cancel(task.id)
  }
}

// Collapsed, the header still tells the main thing: «Backup · 54% · ~2 min · +1».
const active = computed(() => tracker.tasks.value.filter(task => task.status === 'active'))
const summary = computed(() => {
  const [first, ...rest] = active.value
  if (!first) return t('Tasks finished')
  const parts = [first.title]
  if (first.total) parts.push(`${first.percent}%`)
  if (eta(first)) parts.push(eta(first))
  if (rest.length) parts.push(`+${rest.length}`)
  return parts.join(' · ')
})
const overallPercent = computed(() =>
  active.value.length ? Math.round(active.value.reduce((sum, task) => sum + task.percent, 0) / active.value.length) : 100)

/** The stage, with «step 2 of 3» for work in parts while it runs. */
function describe(task: TaskEntry): string {
  const text = task.description ?? ''
  if (task.status !== 'active' || task.cancelling || !task.steps || task.steps < 2 || !task.step) return text
  const [n, m] = [String(task.step), String(task.steps)]
  const step = t('step {n} of {m}', { n, m }).replace('{n}', n).replace('{m}', m)
  return text ? `${text} · ${step}` : step
}

function formatCount(task: TaskEntry): string {
  if (task.unit === 'bytes') return `${formatFileSize(task.count)} / ${formatFileSize(task.total)}`
  const fmt = (n: number) =>
    n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1)}M`
    : n >= 1_000 ? `${(n / 1_000).toFixed(0)}k`
    : String(n)
  return `${fmt(task.count)} / ${fmt(task.total)}`
}

/** "~2 min" left at the recent pace (useTaskTracker measures it) — once it's known. */
function eta(task: TaskEntry): string {
  const left = task.etaSeconds
  if (task.status !== 'active' || left == null) return ''
  if (left < 60) return t('< 1 min')
  const n = String(Math.round(left / 60))
  // Params for a translated key, replace() for one not in the bundle (renders {n} as is).
  return t('~{n} min', { n }).replace('{n}', n)
}
</script>

<template>
  <Teleport to="body">
    <Transition
      enter-active-class="transition duration-200 ease-out"
      enter-from-class="translate-y-2 opacity-0"
      leave-active-class="transition duration-150 ease-in"
      leave-to-class="translate-y-2 opacity-0"
    >
      <div
        v-if="visible"
        ref="panel"
        class="fixed right-6 bottom-6 z-40 w-80 overflow-hidden rounded-lg border bg-popover text-popover-foreground shadow-md"
      >
        <div class="relative flex items-center gap-2 px-3 py-2" :class="{ 'border-b': !collapsed }">
          <span class="flex-1 truncate font-medium tabular-nums">
            <template v-if="collapsed">{{ summary }}</template>
            <template v-else>{{ tracker.hasActive.value ? t('Tasks running') : t('Tasks finished') }}</template>
          </span>
          <Button variant="ghost" size="icon-xs" :aria-label="collapsed ? t('Expand') : t('Collapse')"
            @click="collapsed = !collapsed">
            <ChevronUp v-if="collapsed" />
            <ChevronDown v-else />
          </Button>
          <Progress v-if="collapsed && active.length" :model-value="overallPercent"
            class="absolute inset-x-0 bottom-0 h-0.5 rounded-none" />
        </div>

        <div v-if="!collapsed" class="max-h-96 divide-y overflow-y-auto">
          <div v-for="task in tracker.tasks.value" :key="task.id" class="group space-y-2 px-3 py-2.5">
            <div class="flex items-start gap-2">
              <Spinner v-if="task.status === 'active'" class="mt-px size-3.5 text-muted-foreground" />
              <CircleCheck v-else-if="task.status === 'done'" class="mt-px size-3.5 text-success" />
              <CircleX v-else-if="task.status === 'cancelled'" class="mt-px size-3.5 text-muted-foreground" />
              <CircleAlert v-else class="mt-px size-3.5 text-destructive" />
              <div class="min-w-0 flex-1">
                <p class="truncate font-medium">{{ task.title }}</p>
                <p v-if="describe(task)" class="truncate text-muted-foreground"
                  :class="{ 'text-destructive': task.status === 'error' }">
                  {{ describe(task) }}
                </p>
              </div>
              <Button v-if="task.status !== 'active'" variant="ghost" size="icon-xs"
                class="opacity-0 group-hover:opacity-100" :aria-label="t('Dismiss')"
                @click="tracker.dismiss(task.id)">
                <X />
              </Button>
              <Button v-else-if="task.cancellable" variant="ghost" size="icon-xs"
                :disabled="task.cancelling" :aria-label="t('Cancel task')" :title="t('Cancel task')"
                @click="cancel(task)">
                <X />
              </Button>
            </div>

            <Progress :model-value="task.percent" :class="['h-1.5', `pind-${task.status}`]" />

            <div class="flex items-center justify-between text-muted-foreground tabular-nums">
              <span>{{ task.total ? formatCount(task) : '' }}</span>
              <span v-if="task.total">
                {{ task.percent }}%<template v-if="eta(task)"> · {{ eta(task) }}</template>
              </span>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
/* Stock <Progress> paints the indicator bg-primary; recolour per task status. */
.pind-done :deep([data-slot='progress-indicator']) {
  background-color: var(--success);
}
.pind-error :deep([data-slot='progress-indicator']) {
  background-color: var(--destructive);
}
.pind-cancelled :deep([data-slot='progress-indicator']) {
  background-color: var(--muted-foreground);
}
</style>
