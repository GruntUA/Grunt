<script setup lang="ts">
// CodeMirror wrapper shared by the Code and HTMLEditor fields. Loaded only for
// editable fields - read-only ones render CodeView instead.
import { computed, shallowRef, watch } from 'vue'
import { Codemirror } from 'vue-codemirror'
import { oneDark } from '@codemirror/theme-one-dark'
import type { Extension } from '@codemirror/state'
import { useColorMode } from '@/core/composables/useColorMode'

const props = withDefaults(defineProps<{
  modelValue: string
  lang: string
  minHeight?: string
}>(), { minHeight: '120px' })

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const { isDark } = useColorMode()

// Each grammar is its own chunk - a SQL field never pulls the Python/HTML/… parsers.
const LANG_LOADERS: Record<string, () => Promise<Extension>> = {
  sql: () => import('@codemirror/lang-sql').then((m) => m.sql()),
  js: () => import('@codemirror/lang-javascript').then((m) => m.javascript()),
  javascript: () => import('@codemirror/lang-javascript').then((m) => m.javascript()),
  ts: () => import('@codemirror/lang-javascript').then((m) => m.javascript({ typescript: true })),
  typescript: () => import('@codemirror/lang-javascript').then((m) => m.javascript({ typescript: true })),
  py: () => import('@codemirror/lang-python').then((m) => m.python()),
  python: () => import('@codemirror/lang-python').then((m) => m.python()),
  html: () => import('@codemirror/lang-html').then((m) => m.html()),
  css: () => import('@codemirror/lang-css').then((m) => m.css()),
  json: () => import('@codemirror/lang-json').then((m) => m.json()),
}

// Populated asynchronously - the editor renders immediately, highlighting snaps
// in once the grammar chunk resolves.
const langExt = shallowRef<Extension | null>(null)
watch(
  () => props.lang,
  (l, _prev, onCleanup) => {
    let cancelled = false
    onCleanup(() => { cancelled = true })
    const loader = LANG_LOADERS[l]
    if (!loader) { langExt.value = null; return }
    loader().then((ext) => { if (!cancelled) langExt.value = ext })
  },
  { immediate: true },
)

const extensions = computed<Extension[]>(() => {
  const exts: Extension[] = []
  if (isDark.value) exts.push(oneDark) // default (light) theme otherwise
  if (langExt.value) exts.push(langExt.value)
  return exts
})
</script>

<template>
  <Codemirror
    :model-value="modelValue"
    :extensions="extensions"
    :indent-with-tab="true"
    :tab-size="2"
    :style="{ minHeight }"
    @update:model-value="(v: string) => emit('update:modelValue', v)"
  />
</template>
