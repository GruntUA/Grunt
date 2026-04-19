<script setup lang="ts">
import type { HTMLAttributes } from "vue"
import { cn } from "@/lib/utils"

const props = defineProps<{
  class?: HTMLAttributes["class"]
}>()
</script>

<template>
  <div
    data-slot="scroll-area"
    :class="cn('relative overflow-auto', props.class)"
  >
    <slot />
  </div>
</template>
