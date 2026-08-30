<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { MapPin, ExternalLink } from '@lucide/vue'
import type { BaseFieldProps } from '@/types'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'

const props = defineProps<BaseFieldProps>()
const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const { t } = useI18n()

function num(v: unknown): number | null {
  if (v === null || v === undefined || v === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

const parsed = computed<{ lat: number | null; lng: number | null }>(() => {
  if (props.modelValue && typeof props.modelValue === 'object') {
    const v = props.modelValue as Record<string, unknown>
    return { lat: num(v.lat), lng: num(v.lng) }
  }
  return { lat: null, lng: null }
})

const readonly = computed(() => !!props.disabled || !!props.field.read_only)
const isLocating = ref(false)
const locateError = ref('')

const latOutOfRange = computed(() => parsed.value.lat !== null && Math.abs(parsed.value.lat) > 90)
const lngOutOfRange = computed(() => parsed.value.lng !== null && Math.abs(parsed.value.lng) > 180)

const mapUrl = computed(() => {
  const { lat, lng } = parsed.value
  if (lat === null || lng === null || latOutOfRange.value || lngOutOfRange.value) return null
  return `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lng}#map=15/${lat}/${lng}`
})

function update(key: 'lat' | 'lng', val: string | number) {
  emit('update:modelValue', { ...parsed.value, [key]: num(val) })
}

function parsePaste(e: ClipboardEvent) {
  const text = e.clipboardData?.getData('text') ?? ''
  const m = text.trim().match(/^(-?\d+(?:\.\d+)?)[,\s]+(-?\d+(?:\.\d+)?)$/)
  if (m) {
    e.preventDefault()
    emit('update:modelValue', { lat: Number(m[1]), lng: Number(m[2]) })
  }
}

// Scrolling over a focused number input silently changes it.
function onWheel(e: WheelEvent) {
  if (document.activeElement === e.target) e.preventDefault()
}

function locate() {
  locateError.value = ''
  if (!navigator.geolocation) {
    locateError.value = t('Location unavailable')
    return
  }
  isLocating.value = true
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      emit('update:modelValue', { lat: pos.coords.latitude, lng: pos.coords.longitude })
      isLocating.value = false
    },
    () => {
      locateError.value = t('Could not get your location')
      isLocating.value = false
    },
    { enableHighAccuracy: true, timeout: 10000 },
  )
}
</script>

<template>
  <div class="flex flex-col gap-1.5">
    <div class="flex items-start gap-2">
      <Input
        type="number"
        step="any"
        inputmode="decimal"
        :model-value="parsed.lat ?? ''"
        :disabled="readonly"
        :placeholder="t('Latitude')"
        :aria-label="t('Latitude')"
        :aria-invalid="(error || latOutOfRange) ? true : undefined"
        class="flex-1 tabular-nums"
        min="-90"
        max="90"
        @wheel="onWheel"
        @update:model-value="update('lat', $event)"
        @paste="parsePaste"
      />
      <Input
        type="number"
        step="any"
        inputmode="decimal"
        :model-value="parsed.lng ?? ''"
        :disabled="readonly"
        :placeholder="t('Longitude')"
        :aria-label="t('Longitude')"
        :aria-invalid="(error || lngOutOfRange) ? true : undefined"
        class="flex-1 tabular-nums"
        min="-180"
        max="180"
        @wheel="onWheel"
        @update:model-value="update('lng', $event)"
        @paste="parsePaste"
      />
      <Button
        v-if="!readonly"
        variant="outline"
        type="button"
        size="sm"
        :disabled="isLocating"
        @click="locate"
      >
        <MapPin class="mr-1 size-4" />
        {{ isLocating ? '…' : t('My location') }}
      </Button>
    </div>

    <div class="flex items-center gap-3 text-xs">
      <a
        v-if="mapUrl"
        :href="mapUrl"
        target="_blank"
        rel="noopener noreferrer"
        class="inline-flex items-center gap-1 text-primary hover:underline"
      >
        {{ t('Open in map') }}
        <ExternalLink class="size-3" />
      </a>
      <span v-if="locateError || latOutOfRange || lngOutOfRange" class="text-destructive">
        {{ locateError || t('Coordinates out of range') }}
      </span>
    </div>
  </div>
</template>
