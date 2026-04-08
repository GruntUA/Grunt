<script setup lang="ts">
import { computed } from 'vue'
import { Codemirror } from 'vue-codemirror'
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

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const LANG_MAP: Record<string, () => Extension> = {
  sql:        () => sql(),
  js:         () => javascript(),
  javascript: () => javascript(),
  ts:         () => javascript({ typescript: true }),
  typescript: () => javascript({ typescript: true }),
  py:         () => python(),
  python:     () => python(),
  html:       () => html(),
  css:        () => css(),
  json:       () => json(),
}

const extensions = computed<Extension[]>(() => {
  const lang = (props.field.options ?? '').toLowerCase().trim()
  const exts: Extension[] = [oneDark]
  const langExt = LANG_MAP[lang]?.()
  if (langExt) exts.push(langExt)
  if (props.disabled || props.field.read_only) exts.push(EditorState.readOnly.of(true))
  return exts
})

const value = computed(() => {
  const raw = String(props.modelValue ?? '')
  const lang = (props.field.options ?? '').toLowerCase().trim()
  if (lang === 'sql' && raw) {
    try {
      return formatSql(raw, { language: 'sql', tabWidth: 2, keywordCase: 'upper' })
    } catch {
      return raw
    }
  }
  return raw
})
</script>

<template>
  <div
    class="rounded-md overflow-hidden text-sm border"
    :class="error ? 'border-destructive' : 'border-input'"
  >
    <Codemirror
      :model-value="value"
      :extensions="extensions"
      :indent-with-tab="true"
      :tab-size="2"
      :style="{ minHeight: '120px' }"
      @update:model-value="emit('update:modelValue', $event)"
    />
  </div>
</template>
