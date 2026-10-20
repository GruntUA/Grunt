<script setup lang="ts">
import { computed, defineAsyncComponent, ref, watch } from 'vue'
import type { DocField } from '@/types'
import CodeView from '../Code/CodeView.vue'

// CodeMirror is only fetched for editable fields.
const CodeEditor = defineAsyncComponent(() => import('../Code/CodeEditor.vue'))

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const isReadonly = computed(() => !!props.disabled || !!props.field.read_only)

// The editor is driven by its own buffer; the model is only re-read when it
// changes from *outside* (so typing never triggers a cursor jump).
const buffer = ref(String(props.modelValue ?? ''))
let lastEmitted = ''

watch(
  () => props.modelValue,
  (v) => {
    const s = String(v ?? '')
    if (s !== lastEmitted) buffer.value = s
  },
)

function onChange(v: string) {
  buffer.value = v
  lastEmitted = v
  emit('update:modelValue', v)
}
</script>

<template>
  <CodeView v-if="isReadonly" :code="buffer" language="html" />
  <div
    v-else
    class="overflow-hidden rounded-md border"
    :class="error ? 'border-destructive' : 'border-input'"
  >
    <CodeEditor :model-value="buffer" lang="html" min-height="160px" @update:model-value="onChange" />
  </div>
</template>
