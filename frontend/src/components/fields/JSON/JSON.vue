<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { BaseFieldProps } from '@/types'
import { Textarea } from '@/components/ui/textarea'

const props = defineProps<BaseFieldProps>()
const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const { t } = useI18n()
const localError = ref<string | null>(null)

function formatValue(v: unknown): string {
  if (v === null || v === undefined || v === '') return ''
  if (typeof v === 'string') return v
  try { return JSON.stringify(v, null, 2) } catch { return String(v) }
}

function sig(v: unknown): string {
  try { return JSON.stringify(v) } catch { return String(v) }
}

const text = ref(formatValue(props.modelValue))
let lastEmit = sig(props.modelValue)

// Re-read only when the model changes from outside — our own echo would
// otherwise reformat the textarea mid-typing and jump the caret.
watch(() => props.modelValue, (v) => {
  if (sig(v) === lastEmit) return
  text.value = formatValue(v)
})

function onUpdate(val: string | number) {
  const s = String(val ?? '')
  text.value = s
  localError.value = null
  if (!s.trim()) {
    lastEmit = sig(null)
    emit('update:modelValue', null)
    return
  }
  try {
    const parsed = JSON.parse(s)
    lastEmit = sig(parsed)
    emit('update:modelValue', parsed)
  } catch {
    // wait until blur to complain
  }
}

function onBlur() {
  if (!text.value.trim()) return
  try {
    text.value = JSON.stringify(JSON.parse(text.value), null, 2)
    localError.value = null
  } catch {
    localError.value = t('Invalid JSON')
  }
}
</script>

<template>
  <div class="flex flex-col gap-1">
    <Textarea
      :model-value="text"
      :disabled="disabled || field.read_only"
      :aria-invalid="(error || localError) ? true : undefined"
      :aria-label="field.label"
      rows="6"
      class="max-h-80 w-full resize-y overflow-y-auto font-mono"
      @update:model-value="onUpdate"
      @blur="onBlur"
    />
    <p v-if="localError" class="text-destructive">{{ localError }}</p>
  </div>
</template>
