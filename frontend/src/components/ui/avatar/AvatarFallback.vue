<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { inject, computed } from 'vue'
import { cn } from '@/lib/utils'

const props = defineProps<{ class?: HTMLAttributes['class'] }>()

const ctx = inject<{
  imageStatus: { value: 'idle' | 'loading' | 'loaded' | 'error' }
}>('$avatar')

const visible = computed(() => !ctx || ctx.imageStatus.value !== 'loaded')
</script>

<template>
  <span
    v-show="visible"
    data-slot="avatar-fallback"
    :class="cn('bg-muted flex size-full items-center justify-center rounded-full', props.class)"
  >
    <slot />
  </span>
</template>
