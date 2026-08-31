<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Codemirror } from 'vue-codemirror'
import { Sparkles } from '@lucide/vue'
import { format as formatSql } from 'sql-formatter'
import { sql } from '@codemirror/lang-sql'
import { javascript } from '@codemirror/lang-javascript'
import { python } from '@codemirror/lang-python'
import { html } from '@codemirror/lang-html'
import { css } from '@codemirror/lang-css'
import { json } from '@codemirror/lang-json'
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

const { t } = useI18n()
const { isDark } = useColorMode()

const LANG_MAP: Record<string, () => Extension> = {
  sql: () => sql(),
  js: () => javascript(),
  javascript: () => javascript(),
  ts: () => javascript({ typescript: true }),
  typescript: () => javascript({ typescript: true }),
  py: () => python(),
  python: () => python(),
  html: () => html(),
  css: () => css(),
  json: () => json(),
}

const lang = computed(() => (props.field.options ?? '').toLowerCase().trim())
const canFormat = computed(() => lang.value === 'sql' || lang.value === 'json')
const isReadonly = computed(() => !!props.disabled || !!props.field.read_only)

const extensions = computed<Extension[]>(() => {
  const exts: Extension[] = []
  if (isDark.value) exts.push(oneDark) // default (light) theme otherwise
  const langExt = LANG_MAP[lang.value]?.()
  if (langExt) exts.push(langExt)
  if (isReadonly.value) exts.push(EditorState.readOnly.of(true))
  return exts
})

function fromModel(v: unknown): string {
  if (v === null || v === undefined || v === '') return ''
  if (typeof v === 'string') return v
  try {
    return JSON.stringify(v, null, 2)
  } catch {
    return String(v)
  }
}

function prettify(raw: string): string {
  if (!raw.trim()) return raw
  if (lang.value === 'json') {
    try { return JSON.stringify(JSON.parse(raw), null, 2) } catch { return raw }
  }
  if (lang.value === 'sql') {
    try { return formatSql(raw, { language: 'sql', tabWidth: 2, keywordCase: 'upper' }) } catch { return raw }
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

// Pretty-print the stored value once for readability (no emit → not dirty).
onMounted(() => {
  buffer.value = prettify(buffer.value)
})

function onChange(v: string) {
  buffer.value = v
  lastEmitted = v
  emit('update:modelValue', v)
}

function formatNow() {
  const f = prettify(buffer.value)
  if (f !== buffer.value) onChange(f)
}
</script>

<template>
  <div
    class="overflow-hidden rounded-md border"
    :class="error ? 'border-destructive' : 'border-input'"
  >
    <div
      v-if="canFormat && !isReadonly"
      class="flex justify-end border-b border-border bg-muted/40 px-1.5 py-1"
    >
      <button
        type="button"
        class="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        @click="formatNow"
      >
        <Sparkles class="size-3" />
        {{ t('Format') }}
      </button>
    </div>
    <Codemirror
      :model-value="buffer"
      :extensions="extensions"
      :indent-with-tab="true"
      :tab-size="2"
      :style="{ minHeight: '120px' }"
      @update:model-value="onChange"
    />
  </div>
</template>
