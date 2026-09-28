<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref, computed, onMounted, watch } from 'vue'
import { useElementSize, useNow } from '@vueuse/core'
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
const now = useNow({ interval: 1000 })

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

function formatCount(task: TaskEntry): string {
  if (task.unit === 'bytes') return `${formatFileSize(task.count)} / ${formatFileSize(task.total)}`
  const fmt = (n: number) =>
    n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1)}M`
    : n >= 1_000 ? `${(n / 1_000).toFixed(0)}k`
    : String(n)
  return `${fmt(task.count)} / ${fmt(task.total)}`
}

/** "~2 min" left, extrapolated from the time so far — once there's enough to go on. */
function eta(task: TaskEntry): string {
  if (task.status !== 'active' || task.percent < 3 || task.percent >= 100) return ''
  const elapsed = (now.value.getTime() - task.startedAt) / 1000
  const left = (elapsed * (100 - task.percent)) / task.percent
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
        <div class="flex items-center gap-2 border-b px-3 py-2">
          <Spinner v-if="tracker.hasActive.value" class="text-muted-foreground" />
          <CircleCheck v-else class="size-4 text-success" />
          <span class="flex-1 font-medium">
            {{ tracker.hasActive.value ? t('Tasks running') : t('Tasks finished') }}
          </span>
          <Button variant="ghost" size="icon-xs" :aria-label="collapsed ? t('Expand') : t('Collapse')"
            @click="collapsed = !collapsed">
            <ChevronUp v-if="collapsed" />
            <ChevronDown v-else />
          </Button>
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
                <p v-if="task.description" class="truncate text-muted-foreground"
                  :class="{ 'text-destructive': task.status === 'error' }">
                  {{ task.description }}
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
