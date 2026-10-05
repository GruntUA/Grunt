<script setup lang="ts">
import { computed, onMounted, ref, shallowRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Codemirror } from 'vue-codemirror'
import { Sparkles } from '@lucide/vue'
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

const lang = computed(() => (props.field.options ?? '').toLowerCase().trim())
const canFormat = computed(() => lang.value === 'sql' || lang.value === 'json')
const isReadonly = computed(() => !!props.disabled || !!props.field.read_only)

// Populated asynchronously - the editor renders immediately, highlighting snaps
// in once the grammar chunk resolves.
const langExt = shallowRef<Extension | null>(null)
watch(
  lang,
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
        class="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
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
