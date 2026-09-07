<script setup lang="ts">
import type { HTMLAttributes } from "vue"
import { ReloadIcon } from '@radix-icons/vue'
import { cn } from "@/lib/utils"

const props = defineProps<{
  class?: HTMLAttributes["class"]
}>()
</script>

<template>
  <ReloadIcon role="status" aria-label="Loading" :class="cn('size-4 animate-spin', props.class)" />
</template>
