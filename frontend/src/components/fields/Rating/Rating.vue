<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Star, StarHalf } from '@lucide/vue'
import type { BaseFieldProps } from '@/types'

const props = defineProps<BaseFieldProps>()
const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const { t } = useI18n()

const maxStars = computed(() => Math.max(1, Math.round(props.field.max_value ?? 5)))
const value = computed(() => {
  const v = Number(props.modelValue)
  return Number.isFinite(v) ? Math.min(Math.max(v, 0), maxStars.value) : 0
})
const readonly = computed(() => !!props.disabled || !!props.field.read_only)

const hoverStar = ref<number | null>(null)
const shown = computed(() => hoverStar.value ?? value.value)

function fill(i: number): 'full' | 'half' | 'empty' {
  if (shown.value >= i) return 'full'
  if (shown.value >= i - 0.5) return 'half'
  return 'empty'
}

function setValue(star: number) {
  if (readonly.value) return
  emit('update:modelValue', value.value === star ? null : star)
}

function onKeydown(e: KeyboardEvent) {
  if (readonly.value) return
  const cur = value.value || 0
  let next = cur
  if (e.key === 'ArrowRight' || e.key === 'ArrowUp') next = Math.min(maxStars.value, cur + 1)
  else if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') next = Math.max(0, cur - 1)
  else if (e.key === 'Home') next = 1
  else if (e.key === 'End') next = maxStars.value
  else return
  e.preventDefault()
  emit('update:modelValue', next === 0 ? null : next)
}
</script>

<template>
  <div
    class="inline-flex items-center gap-1 rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
    role="slider"
    :aria-label="field.label"
    :aria-valuemin="0"
    :aria-valuemax="maxStars"
    :aria-valuenow="value"
    :aria-valuetext="t('{n} of {max}', { n: value, max: maxStars })"
    :aria-invalid="error ? true : undefined"
    :aria-readonly="readonly || undefined"
    :tabindex="readonly ? -1 : 0"
    @keydown="onKeydown"
    @mouseleave="hoverStar = null"
  >
    <button
      v-for="i in maxStars"
      :key="i"
      type="button"
      tabindex="-1"
      :disabled="readonly"
      :aria-label="t('Rate {n}', { n: i })"
      class="disabled:cursor-default"
      :class="readonly ? '' : 'cursor-pointer'"
      @mouseenter="!readonly && (hoverStar = i)"
      @click="setValue(i)"
    >
      <span v-if="fill(i) === 'half'" class="relative inline-flex size-6">
        <Star class="absolute inset-0 size-6 fill-transparent text-muted-foreground/40" />
        <StarHalf class="absolute inset-0 size-6 fill-warning text-warning" />
      </span>
      <Star
        v-else
        class="size-6"
        :class="fill(i) === 'full' ? 'fill-warning text-warning' : 'fill-transparent text-muted-foreground/40'"
      />
    </button>
    <span v-if="value" class="ml-1.5 text-muted-foreground tabular-nums">{{ value }}</span>
  </div>
</template>
