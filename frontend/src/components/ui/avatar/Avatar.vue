<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { ref, provide } from 'vue'
import { cn } from '@/lib/utils'

const props = defineProps<{ class?: HTMLAttributes['class'] }>()

const imageStatus = ref<'idle' | 'loading' | 'loaded' | 'error'>('idle')
provide('$avatar', {
  imageStatus,
  setStatus: (s: 'idle' | 'loading' | 'loaded' | 'error') => { imageStatus.value = s },
})
</script>

<template>
  <div
    data-slot="avatar"
    :class="cn('relative flex size-8 shrink-0 overflow-hidden rounded-full', props.class)"
  >
    <slot />
  </div>
</template>
