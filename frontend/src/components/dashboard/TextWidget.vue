<script setup lang="ts">
import type { DashboardWidget } from '@/types'

defineProps<{ widget: DashboardWidget }>()
</script>

<template>
  <div class="flex flex-col h-full overflow-hidden">
    <div v-if="widget.title" class="px-5 pt-4 pb-1 shrink-0">
      <p class="font-semibold text-foreground">{{ widget.title }}</p>
      <p v-if="widget.description" class="text-xs text-muted-foreground">{{ widget.description }}</p>
    </div>
    <!-- eslint-disable-next-line vue/no-v-html -->
    <div
      class="flex-1 px-5 py-3 overflow-auto text-foreground/90 leading-relaxed [&_a]:text-primary [&_a]:underline [&_strong]:font-semibold [&_ul]:list-disc [&_ul]:pl-4 [&_ol]:list-decimal [&_ol]:pl-4"
      v-html="widget.content ?? ''"
    />
  </div>
</template>
