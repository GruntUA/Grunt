<script setup lang="ts">
import { ref, computed } from 'vue'
import { CheckCircle2, AlertCircle, ChevronDown, ChevronUp, X, Settings2 } from '@lucide/vue'
import { useTaskTracker } from '@/core/composables/useTaskTracker'
import { Progress } from '@/components/ui/progress'

const tracker = useTaskTracker()
const collapsed = ref(false)

const visible = computed(() => tracker.count.value > 0)

function statusIcon(status: 'active' | 'done' | 'error') {
  if (status === 'done') return CheckCircle2
  if (status === 'error') return AlertCircle
  return Settings2
}

function formatCount(count: number, total: number): string {
  const fmt = (n: number) =>
    n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1)}M`
    : n >= 1_000 ? `${(n / 1_000).toFixed(0)}k`
    : String(n)
  return `${fmt(count)} / ${fmt(total)}`
}
</script>

<template>
  <Teleport to="body">
    <Transition
      enter-active-class="transition-all duration-300 ease-out"
      enter-from-class="translate-y-4 opacity-0"
      enter-to-class="translate-y-0 opacity-100"
      leave-active-class="transition-all duration-200 ease-in"
      leave-from-class="translate-y-0 opacity-100"
      leave-to-class="translate-y-4 opacity-0"
    >
      <div
        v-if="visible"
        class="fixed bottom-6 right-6 z-40 w-80 rounded-lg border border-border/60
               bg-popover shadow-md overflow-hidden"
      >
        <!-- Header -->
        <div class="flex items-center gap-2 px-4 py-2.5 border-b border-border/40 bg-muted/20">
          <div
            v-if="tracker.hasActive.value"
            class="size-4 rounded-full border-2 border-primary/30 border-t-primary animate-spin shrink-0"
          />
          <CheckCircle2 v-else class="size-4 text-success shrink-0" />

          <span class="font-semibold text-foreground flex-1">
            {{ tracker.hasActive.value ? 'Виконуються задачі' : 'Задачі завершено' }}
          </span>

          <button
            type="button"
            class="size-6 flex items-center justify-center rounded-lg text-muted-foreground
                   hover:text-foreground hover:bg-muted/50 transition-colors"
            @click="collapsed = !collapsed"
          >
            <ChevronDown v-if="!collapsed" class="size-3.5" />
            <ChevronUp v-else class="size-3.5" />
          </button>
        </div>

        <!-- Task list -->
        <Transition
          enter-active-class="transition-all duration-200 ease-out"
          enter-from-class="opacity-0 max-h-0"
          enter-to-class="opacity-100 max-h-[400px]"
          leave-active-class="transition-all duration-150 ease-in"
          leave-from-class="opacity-100 max-h-[400px]"
          leave-to-class="opacity-0 max-h-0"
        >
          <div v-if="!collapsed" class="max-h-[400px] overflow-y-auto divide-y divide-border/30">
            <TransitionGroup
              enter-active-class="transition-all duration-200"
              enter-from-class="opacity-0 -translate-y-2"
              enter-to-class="opacity-100 translate-y-0"
              leave-active-class="transition-all duration-150"
              leave-from-class="opacity-100"
              leave-to-class="opacity-0"
            >
              <div
                v-for="task in tracker.tasks.value"
                :key="task.id"
                class="px-4 py-3 group"
                :class="{
                  'opacity-75': task.status === 'done',
                  'bg-destructive/5': task.status === 'error',
                }"
              >
                <!-- Task header row -->
                <div class="flex items-start gap-2 mb-2">
                  <!-- Status icon -->
                  <div class="mt-0.5 shrink-0">
                    <div
                      v-if="task.status === 'active'"
                      class="size-3.5 rounded-full border-2 border-primary/30 border-t-primary animate-spin"
                    />
                    <component
                      v-else
                      :is="statusIcon(task.status)"
                      class="size-3.5"
                      :class="{
                        'text-success': task.status === 'done',
                        'text-destructive': task.status === 'error',
                      }"
                    />
                  </div>

                  <!-- Title + description -->
                  <div class="flex-1 min-w-0">
                    <p class="font-semibold text-foreground truncate leading-tight">
                      {{ task.title }}
                    </p>
                    <p v-if="task.description" class="text-muted-foreground truncate mt-0.5">
                      {{ task.description }}
                    </p>
                  </div>

                  <!-- Dismiss button -->
                  <button
                    type="button"
                    class="shrink-0 opacity-0 group-hover:opacity-100 size-5 flex items-center
                           justify-center rounded text-muted-foreground hover:text-foreground
                           hover:bg-muted/50 transition-all"
                    @click="tracker.dismiss(task.id)"
                  >
                    <X class="size-3" />
                  </button>
                </div>

                <!-- Progress bar -->
                <Progress
                  :model-value="task.percent"
                  class="h-1.5 rounded-full bg-muted/60"
                  :indicator-class="[
                    'rounded-full transition-all duration-500',
                    task.status === 'error'
                      ? 'bg-destructive'
                      : task.status === 'done'
                      ? 'bg-success'
                      : 'bg-primary',
                  ]"
                />

                <!-- Count + percent -->
                <div class="flex items-center justify-between mt-1.5">
                  <span class="text-muted-foreground tabular-nums">
                    {{ formatCount(task.count, task.total) }}
                  </span>
                  <span
                    class="font-semibold tabular-nums"
                    :class="{
                      'text-primary': task.status === 'active',
                      'text-success': task.status === 'done',
                      'text-destructive': task.status === 'error',
                    }"
                  >
                    {{ task.percent }}%
                  </span>
                </div>
              </div>
            </TransitionGroup>
          </div>
        </Transition>
      </div>
    </Transition>
  </Teleport>
</template>
