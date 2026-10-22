<script setup lang="ts">
import { defineAsyncComponent, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Sparkles } from '@lucide/vue'
import type { BaseFieldProps } from '@/types'
import { Button } from '@/components/ui/button'
import CodeView from '../Code/CodeView.vue'

// CodeMirror is only fetched for editable fields.
const CodeEditor = defineAsyncComponent(() => import('../Code/CodeEditor.vue'))

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

// Re-read only when the model changes from outside - our own echo would
// otherwise reformat the textarea mid-typing and jump the caret.
watch(() => props.modelValue, (v) => {
  if (sig(v) === lastEmit) return
  text.value = formatValue(v)
})

function onUpdate(s: string) {
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
    JSON.parse(text.value)
    localError.value = null
  } catch {
    localError.value = t('Invalid JSON')
  }
}

function formatNow() {
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
  <CodeView v-if="disabled || field.read_only" :code="text" language="json" />
  <div v-else class="flex flex-col gap-1">
    <div
      class="overflow-hidden rounded-md border"
      :class="(error || localError) ? 'border-destructive' : 'border-input'"
    >
      <div class="flex justify-end border-b border-border bg-muted/40 px-1.5 py-1">
        <Button type="button" variant="ghost" size="xs" class="text-muted-foreground" @click="formatNow">
          <Sparkles />
          {{ t('Format') }}
        </Button>
      </div>
      <CodeEditor :model-value="text" lang="json" @update:model-value="onUpdate" @blur="onBlur" />
    </div>
    <p v-if="localError" class="text-destructive">{{ localError }}</p>
  </div>
</template>
