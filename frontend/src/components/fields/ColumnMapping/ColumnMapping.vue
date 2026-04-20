<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { Loader2, AlertCircle, CheckCircle2 } from '@lucide/vue'
import type { DocField } from '@/types'
import api from '@/core/api/client'

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
  doc?: Record<string, unknown>
}>()

const emit = defineEmits<{
  'update:modelValue': [value: unknown]
}>()

interface PreviewData {
  headers: string[]
  preview_rows: string[][]
  suggested_mapping: Record<string, string>
  doctype_fields: { fieldname: string; label: string; fieldtype: string; required: boolean }[]
}

const loading = ref(false)
const fetchError = ref('')
const preview = ref<PreviewData | null>(null)

const mapping = computed<Record<string, string>>(() => {
  if (!props.modelValue) return {}
  if (typeof props.modelValue === 'string') {
    try { return JSON.parse(props.modelValue) } catch { return {} }
  }
  return props.modelValue as Record<string, string>
})

function storageKey(doctype: string) {
  return `grunt_col_mapping:${doctype}`
}

function saveToStorage(doctype: string, m: Record<string, string>) {
  try { localStorage.setItem(storageKey(doctype), JSON.stringify(m)) } catch {}
}

function loadFromStorage(doctype: string): Record<string, string> | null {
  try {
    const raw = localStorage.getItem(storageKey(doctype))
    return raw ? JSON.parse(raw) : null
  } catch { return null }
}

async function fetchPreview() {
  const docId = props.doc?.id
  const file = props.doc?.file
  const doctype = props.doc?.doctype_name as string | undefined

  if (!docId || !file || !doctype) {
    preview.value = null
    return
  }

  loading.value = true
  fetchError.value = ''
  try {
    const res = await api.get('/api/v1/method/grunt.api.v1.data_import.get_import_preview', {
      params: { data_import_id: docId },
    })
    preview.value = res.data.data
    // Pre-fill: 1) saved mapping, 2) API suggestion, 3) nothing
    if (!props.modelValue || Object.keys(mapping.value).length === 0) {
      const saved = loadFromStorage(doctype)
      emit('update:modelValue', saved ?? res.data.data.suggested_mapping)
    }
  } catch (e: any) {
    fetchError.value = e.response?.data?.error?.message || 'Помилка завантаження попереднього перегляду'
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.doc?.file, props.doc?.doctype_name],
  () => fetchPreview(),
  { immediate: true }
)

function setMapping(header: string, fieldname: string) {
  const updated = { ...mapping.value, [header]: fieldname }
  const doctype = props.doc?.doctype_name as string | undefined
  if (doctype) saveToStorage(doctype, updated)
  emit('update:modelValue', updated)
}

const mappedCount = computed(() =>
  Object.values(mapping.value).filter(Boolean).length
)

const requiredMissing = computed(() => {
  if (!preview.value) return []
  const mapped = new Set(Object.values(mapping.value).filter(Boolean))
  return preview.value.doctype_fields.filter(f => f.required && !mapped.has(f.fieldname))
})
</script>

<template>
  <div class="space-y-3">
    <!-- Loading -->
    <div v-if="loading" class="flex items-center gap-2 text-sm text-muted-foreground py-4">
      <Loader2 class="size-4 animate-spin" />
      Завантаження структури файлу...
    </div>

    <!-- No file/doctype selected -->
    <div v-else-if="!doc?.file || !doc?.doctype_name"
      class="text-sm text-muted-foreground py-3 px-4 bg-muted/40 rounded-lg border border-dashed">
      Спочатку оберіть DocType та завантажте файл
    </div>

    <!-- Error -->
    <div v-else-if="fetchError"
      class="flex items-center gap-2 text-sm text-destructive py-3 px-4 bg-destructive/10 rounded-lg">
      <AlertCircle class="size-4 shrink-0" />
      {{ fetchError }}
    </div>

    <!-- Mapping table -->
    <template v-else-if="preview">
      <!-- Status bar -->
      <div class="flex items-center justify-between text-xs text-muted-foreground">
        <span>{{ preview.headers.length }} колонок у файлі</span>
        <span class="flex items-center gap-1.5">
          <CheckCircle2 class="size-3.5 text-green-500" />
          {{ mappedCount }} з {{ preview.headers.length }} прив'язано
        </span>
      </div>

      <!-- Required fields warning -->
      <div v-if="requiredMissing.length > 0"
        class="flex items-start gap-2 text-xs text-amber-600 dark:text-amber-400 py-2 px-3 bg-amber-50 dark:bg-amber-950/30 rounded-lg border border-amber-200 dark:border-amber-800">
        <AlertCircle class="size-3.5 shrink-0 mt-0.5" />
        <span>Обов'язкові поля без маппінгу: <strong>{{ requiredMissing.map(f => f.label).join(', ') }}</strong></span>
      </div>

      <div class="rounded-lg border overflow-hidden">
        <table class="w-full text-sm">
          <thead class="bg-muted/60 border-b">
            <tr>
              <th class="px-3 py-2 text-left font-medium text-muted-foreground w-[40%]">Колонка файлу</th>
              <th class="px-3 py-2 text-left font-medium text-muted-foreground">Поле системи</th>
              <th class="px-3 py-2 text-left font-medium text-muted-foreground text-[11px] hidden lg:table-cell">
                Приклад даних
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(header, idx) in preview.headers" :key="header"
              class="border-b last:border-0 hover:bg-muted/30 transition-colors"
              :class="mapping[header] ? '' : 'opacity-60'">
              <td class="px-3 py-2 font-mono text-xs font-medium">{{ header }}</td>
              <td class="px-3 py-2">
                <select
                  :value="mapping[header] || ''"
                  :disabled="disabled"
                  class="w-full text-sm border rounded px-2 py-1 bg-background text-foreground disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-ring"
                  @change="setMapping(header, ($event.target as HTMLSelectElement).value)">
                  <option value="">— Не імпортувати —</option>
                  <option v-for="f in preview.doctype_fields" :key="f.fieldname" :value="f.fieldname">
                    {{ f.label }}{{ f.required ? ' *' : '' }}
                  </option>
                </select>
              </td>
              <td class="px-3 py-2 text-xs text-muted-foreground font-mono hidden lg:table-cell truncate max-w-[160px]">
                {{ preview.preview_rows[0]?.[idx] ?? '' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Preview rows -->
      <details class="group">
        <summary class="text-xs text-muted-foreground cursor-pointer hover:text-foreground select-none">
          Показати перші рядки файлу ({{ preview.preview_rows.length }})
        </summary>
        <div class="mt-2 overflow-x-auto rounded-lg border text-xs">
          <table class="w-full">
            <thead class="bg-muted/60 border-b">
              <tr>
                <th v-for="h in preview.headers" :key="h" class="px-2 py-1.5 text-left font-mono whitespace-nowrap">
                  {{ h }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, ri) in preview.preview_rows" :key="ri" class="border-b last:border-0">
                <td v-for="(cell, ci) in row" :key="ci" class="px-2 py-1.5 font-mono text-muted-foreground truncate max-w-[140px]">
                  {{ cell }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </details>
    </template>
  </div>
</template>
