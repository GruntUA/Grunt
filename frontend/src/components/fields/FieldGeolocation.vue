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

const parsed = computed<{ lat: number | null; lng: number | null }>(() => {
  if (props.modelValue && typeof props.modelValue === 'object') {
    const v = props.modelValue as Record<string, unknown>
    return { lat: Number(v.lat) || null, lng: Number(v.lng) || null }
  }
  return { lat: null, lng: null }
})

const isLocating = ref(false)

function update(key: 'lat' | 'lng', val: string) {
  const num = val === '' ? null : Number(val)
  emit('update:modelValue', { ...parsed.value, [key]: num })
}

function locate() {
  if (!navigator.geolocation) return
  isLocating.value = true
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      emit('update:modelValue', { lat: pos.coords.latitude, lng: pos.coords.longitude })
      isLocating.value = false
    },
    () => { isLocating.value = false }
  )
}
</script>

<template>
  <div class="flex flex-col gap-1">
    <label class="text-sm font-medium text-[--grunt-text-primary]">
      {{ field.label }}<span v-if="field.required" class="text-[--grunt-danger] ml-0.5">*</span>
    </label>
    <div class="flex gap-2 items-start">
      <div class="flex-1">
        <input
          type="number"
          step="any"
          :value="parsed.lat ?? ''"
          :disabled="disabled || field.read_only"
          placeholder="Latitude"
          class="w-full rounded-[--grunt-radius-sm] border border-[--grunt-border] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[--grunt-primary]/30 focus:border-[--grunt-primary] disabled:bg-[--grunt-surface-secondary]"
          @input="update('lat', ($event.target as HTMLInputElement).value)"
        />
      </div>
      <div class="flex-1">
        <input
          type="number"
          step="any"
          :value="parsed.lng ?? ''"
          :disabled="disabled || field.read_only"
          placeholder="Longitude"
          class="w-full rounded-[--grunt-radius-sm] border border-[--grunt-border] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[--grunt-primary]/30 focus:border-[--grunt-primary] disabled:bg-[--grunt-surface-secondary]"
          @input="update('lng', ($event.target as HTMLInputElement).value)"
        />
      </div>
      <button
        v-if="!disabled && !field.read_only"
        type="button"
        :disabled="isLocating"
        class="px-3 py-2 text-sm border border-[--grunt-border] rounded-[--grunt-radius-sm] hover:bg-[--grunt-surface-secondary] transition-colors whitespace-nowrap disabled:opacity-50"
        @click="locate"
      >{{ isLocating ? '...' : '📍 Моє місце' }}</button>
    </div>
    <p v-if="error" class="text-xs text-[--grunt-danger]">{{ error }}</p>
  </div>
</template>
