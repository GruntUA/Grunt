<script setup lang="ts">
import { ref, computed } from 'vue'
import type { DocField } from '@/types'

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const maxStars = computed(() => Math.round(props.field.max_value ?? 5))
const value = computed(() => {
  const v = Number(props.modelValue)
  return isNaN(v) ? 0 : v
})

// Hover state (only in edit mode)
const hoverStar = ref<number | null>(null)

function starFill(index: number): 'full' | 'half' | 'empty' {
  const display = hoverStar.value !== null ? hoverStar.value : value.value
  if (display >= index) return 'full'
  if (display >= index - 0.5) return 'half'
  return 'empty'
}

function setValue(star: number) {
  if (props.disabled || props.field.read_only) return
  // Clicking the same value clears it
  emit('update:modelValue', value.value === star ? null : star)
}
</script>

<template>
  <div class="flex items-center gap-1" :class="disabled || field.read_only ? 'opacity-70 cursor-default' : 'cursor-pointer'"
    @mouseleave="hoverStar = null">
    <button
      v-for="i in maxStars"
      :key="i"
      type="button"
      class="focus:outline-none"
      :class="disabled || field.read_only ? 'pointer-events-none' : ''"
      @mouseenter="!disabled && !field.read_only && (hoverStar = i)"
      @click="setValue(i)"
    >
      <!-- Full star -->
      <svg v-if="starFill(i) === 'full'" xmlns="http://www.w3.org/2000/svg" class="size-6 text-amber-400" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
      </svg>
      <!-- Half star -->
      <svg v-else-if="starFill(i) === 'half'" xmlns="http://www.w3.org/2000/svg" class="size-6" viewBox="0 0 24 24">
        <defs>
          <linearGradient :id="`half-${i}`">
            <stop offset="50%" stop-color="#fbbf24"/>
            <stop offset="50%" style="stop-color: var(--border)"/>
          </linearGradient>
        </defs>
        <path :fill="`url(#half-${i})`" d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
      </svg>
      <!-- Empty star -->
      <svg v-else xmlns="http://www.w3.org/2000/svg" class="size-6 text-border" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
      </svg>
    </button>
    <span v-if="value" class="ml-1.5 text-muted-foreground tabular-nums">{{ value }}</span>
  </div>
</template>
