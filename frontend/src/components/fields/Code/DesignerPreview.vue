<script setup lang="ts">
import type { DocField } from '@/types'
defineProps<{ field: DocField }>()
</script>

<template>
  <div class="rounded border border-border overflow-hidden">
    <div class="flex items-center gap-1.5 px-2 py-1 bg-zinc-800 border-b border-zinc-700">
      <div class="size-2 rounded-full bg-red-400/80" />
      <div class="size-2 rounded-full bg-yellow-400/80" />
      <div class="size-2 rounded-full bg-green-400/80" />
      <span class="ml-auto text-[10px] text-zinc-400/60 font-mono">{{ field.options ?? 'js' }}</span>
    </div>
    <div class="px-3 py-2 bg-zinc-900 font-mono text-[11px] leading-relaxed">
      <span class="text-purple-400">const </span>
      <span class="text-blue-300">value</span>
      <span class="text-zinc-400"> = </span>
      <span class="text-green-300">"…"</span>
    </div>
  </div>
</template>
