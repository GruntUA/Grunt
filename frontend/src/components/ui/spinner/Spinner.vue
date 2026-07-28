<script setup lang="ts">
import type { HTMLAttributes } from "vue"
import { Loader2 } from "@lucide/vue"
import { cn } from "@/lib/utils"

const props = defineProps<{
  class?: HTMLAttributes["class"]
}>()
</script>

<template>
  <Loader2 data-slot="spinner" :class="cn('animate-spin', props.class)" />
</template>
