<script setup lang="ts">
import { computed, ref, shallowRef, watch } from 'vue'
import { Codemirror } from 'vue-codemirror'
import { oneDark } from '@codemirror/theme-one-dark'
import { EditorState } from '@codemirror/state'
import type { Extension } from '@codemirror/state'
import type { DocField } from '@/types'
import { useColorMode } from '@/core/composables/useColorMode'

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const { isDark } = useColorMode()

const isReadonly = computed(() => !!props.disabled || !!props.field.read_only)

const htmlExt = shallowRef<Extension | null>(null)
import('@codemirror/lang-html').then((m) => { htmlExt.value = m.html() })

const extensions = computed<Extension[]>(() => {
  const exts: Extension[] = []
  if (isDark.value) exts.push(oneDark) // default (light) theme otherwise
  if (htmlExt.value) exts.push(htmlExt.value)
  if (isReadonly.value) exts.push(EditorState.readOnly.of(true))
  return exts
})

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
  <div
    class="overflow-hidden rounded-md border"
    :class="error ? 'border-destructive' : 'border-input'"
  >
    <Codemirror
      :model-value="buffer"
      :extensions="extensions"
      :indent-with-tab="true"
      :tab-size="2"
      :style="{ minHeight: '160px' }"
      @update:model-value="onChange"
    />
  </div>
</template>
