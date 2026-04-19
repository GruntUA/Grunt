<script setup lang="ts">
import { ref, computed } from 'vue'
import type { DocField } from '@/types'
import { MapPin } from '@lucide/vue'

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

function parsePaste(e: ClipboardEvent) {
  const text = e.clipboardData?.getData('text') ?? ''
  const match = text.trim().match(/^(-?\d+(?:\.\d+)?)[,\s]+(-?\d+(?:\.\d+)?)$/)
  if (match) {
    e.preventDefault()
    emit('update:modelValue', { lat: Number(match[1]), lng: Number(match[2]) })
  }
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
  <div class="flex gap-2 items-start">
    <div class="flex-1">
      <input
        type="number"
        step="any"
        :value="parsed.lat ?? ''"
        :disabled="disabled || field.read_only"
        placeholder="Latitude"
        class="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:bg-muted disabled:cursor-not-allowed"
        @input="update('lat', ($event.target as HTMLInputElement).value)"
        @paste="parsePaste"
      />
    </div>
    <div class="flex-1">
      <input
        type="number"
        step="any"
        :value="parsed.lng ?? ''"
        :disabled="disabled || field.read_only"
        placeholder="Longitude"
        class="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:bg-muted disabled:cursor-not-allowed"
        @input="update('lng', ($event.target as HTMLInputElement).value)"
        @paste="parsePaste"
      />
    </div>
    <Button
      v-if="!disabled && !field.read_only"
      type="button" outlined size="small"
      :disabled="isLocating"
      @click="locate"
    >
      <MapPin class="size-4 mr-1" />
      {{ isLocating ? '...' : 'Моє місце' }}
    </Button>
  </div>
</template>
