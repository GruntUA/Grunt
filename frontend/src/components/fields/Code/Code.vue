<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Sparkles } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import type { DocField } from '@/types'
import CodeView from './CodeView.vue'

// CodeMirror is only fetched for editable fields.
const CodeEditor = defineAsyncComponent(() => import('./CodeEditor.vue'))

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const { t } = useI18n()

const lang = computed(() => (props.field.options ?? '').toLowerCase().trim())
const canFormat = computed(() => lang.value === 'sql' || lang.value === 'json')
const isReadonly = computed(() => !!props.disabled || !!props.field.read_only)

function fromModel(v: unknown): string {
  if (v === null || v === undefined || v === '') return ''
  if (typeof v === 'string') return v
  try {
    return JSON.stringify(v, null, 2)
  } catch {
    return String(v)
  }
}

async function prettify(raw: string): Promise<string> {
  if (!raw.trim()) return raw
  if (lang.value === 'json') {
    try { return JSON.stringify(JSON.parse(raw), null, 2) } catch { return raw }
  }
  if (lang.value === 'sql') {
    // sql-formatter (~40 kB) is only pulled for SQL fields, and only lazily.
    try {
      const { format } = await import('sql-formatter')
      return format(raw, { language: 'sql', tabWidth: 2, keywordCase: 'upper' })
    } catch { return raw }
  }
  return raw
}

// The editor is driven by its own buffer; the model is only re-read when it
// changes from *outside* (so typing never triggers a reformat / cursor jump).
const buffer = ref(fromModel(props.modelValue))
let lastEmitted = ''

watch(
  () => props.modelValue,
  (v) => {
    const s = fromModel(v)
    if (s !== lastEmitted) buffer.value = s
  },
)

// Pretty-print the stored value once for readability (no emit -> not dirty).
onMounted(async () => {
  buffer.value = await prettify(buffer.value)
})

function onChange(v: string) {
  buffer.value = v
  lastEmitted = v
  emit('update:modelValue', v)
}

async function formatNow() {
  const f = await prettify(buffer.value)
  if (f !== buffer.value) onChange(f)
}
</script>

<template>
  <CodeView v-if="isReadonly" :code="buffer" :language="lang" />
  <div
    v-else
    class="overflow-hidden rounded-md border"
    :class="error ? 'border-destructive' : 'border-input'"
  >
    <div
      v-if="canFormat"
      class="flex justify-end border-b border-border bg-muted/40 px-1.5 py-1"
    >
      <Button type="button" variant="ghost" size="xs" class="text-muted-foreground" @click="formatNow">
        <Sparkles />
        {{ t('Format') }}
      </Button>
    </div>
    <CodeEditor :model-value="buffer" :lang="lang" @update:model-value="onChange" />
  </div>
</template>
