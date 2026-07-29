<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import type { DashboardWidget } from '@/types'

defineProps<{ widget: DashboardWidget }>()

const now = ref(new Date())
let timer: ReturnType<typeof setInterval>

onMounted(() => { timer = setInterval(() => { now.value = new Date() }, 1000) })
onUnmounted(() => clearInterval(timer))

function pad(n: number) { return n.toString().padStart(2, '0') }

const timeStr = computed(() => {
  const d = now.value
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
})

const dateStr = computed(() =>
  now.value.toLocaleDateString('uk-UA', { weekday: 'long', day: 'numeric', month: 'long' })
)
</script>

<template>
  <div class="flex flex-col items-center justify-center gap-1 h-full p-5 text-center select-none">
    <p v-if="widget.title" class="text-xs text-muted-foreground font-medium uppercase tracking-wide mb-1">
      {{ widget.title }}
    </p>
    <p class="text-4xl font-semibold tabular-nums tracking-tight font-mono leading-none">{{ timeStr }}</p>
    <p class="text-sm text-muted-foreground mt-1 capitalize">{{ dateStr }}</p>
    <p v-if="widget.description" class="text-xs text-muted-foreground mt-1 italic opacity-70">
      {{ widget.description }}
    </p>
  </div>
</template>
