<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Loader2, AlertCircle, CheckCircle2 } from '@lucide/vue'
import type { BaseFieldProps } from '@/types'
import api from '@/core/api/client'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

const props = defineProps<BaseFieldProps>()
const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const { t } = useI18n()

interface PreviewData {
  headers: string[]
  preview_rows: string[][]
  suggested_mapping: Record<string, string>
  doctype_fields: { fieldname: string; label: string; fieldtype: string; required: boolean }[]
}

const loading = ref(false)
const fetchError = ref('')
const preview = ref<PreviewData | null>(null)

const readonly = computed(() => !!props.disabled || !!props.field.read_only)

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
  try { localStorage.setItem(storageKey(doctype), JSON.stringify(m)) } catch { /* private mode */ }
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
  } catch (e: unknown) {
    const err = e as { response?: { data?: { error?: { message?: string } } } }
    fetchError.value = err.response?.data?.error?.message || t('Failed to load preview')
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.doc?.file, props.doc?.doctype_name],
  () => fetchPreview(),
  { immediate: true },
)

function setMapping(header: string, fieldname: string) {
  const updated = { ...mapping.value, [header]: fieldname }
  const doctype = props.doc?.doctype_name as string | undefined
  if (doctype) saveToStorage(doctype, updated)
  emit('update:modelValue', updated)
}

const mappedCount = computed(() => Object.values(mapping.value).filter(Boolean).length)

const requiredMissing = computed(() => {
  if (!preview.value) return []
  const mapped = new Set(Object.values(mapping.value).filter(Boolean))
  return preview.value.doctype_fields.filter((f) => f.required && !mapped.has(f.fieldname))
})
</script>

<template>
  <div class="space-y-3">
    <!-- Loading -->
    <div v-if="loading" class="flex items-center gap-2 text-muted-foreground py-4">
      <Loader2 class="size-4 animate-spin" />
      {{ t('Reading file structure…') }}
    </div>

    <!-- No file/doctype selected -->
    <div v-else-if="!doc?.file || !doc?.doctype_name"
      class="text-muted-foreground py-3 px-4 bg-muted/40 rounded-lg border border-dashed">
      {{ t('First choose a DocType and upload a file') }}
    </div>

    <!-- Error -->
    <div v-else-if="fetchError" role="alert"
      class="flex items-center gap-2 text-destructive py-3 px-4 bg-destructive/10 rounded-lg">
      <AlertCircle class="size-4 shrink-0" />
      {{ fetchError }}
    </div>

    <!-- Mapping table -->
    <template v-else-if="preview">
      <!-- Status bar -->
      <div class="flex items-center justify-between text-xs text-muted-foreground">
        <span>{{ t('{n} columns in file', { n: preview.headers.length }) }}</span>
        <span class="flex items-center gap-1.5">
          <CheckCircle2 class="size-3.5 text-success" />
          {{ t('{mapped} of {total} mapped', { mapped: mappedCount, total: preview.headers.length }) }}
        </span>
      </div>

      <!-- Required fields warning -->
      <div v-if="requiredMissing.length > 0"
        class="flex items-start gap-2 text-xs text-warning py-2 px-3 bg-warning/10 rounded-lg border border-warning/20">
        <AlertCircle class="size-3.5 shrink-0 mt-0.5" />
        <span>
          {{ t('Required fields not mapped:') }}
          <strong>{{ requiredMissing.map((f) => f.label).join(', ') }}</strong>
        </span>
      </div>

      <div class="rounded-lg border overflow-hidden [&_[data-slot=native-select-wrapper]]:w-full">
        <Table>
          <TableHeader>
            <TableRow class="bg-muted/60">
              <TableHead class="w-[40%]">{{ t('File column') }}</TableHead>
              <TableHead>{{ t('System field') }}</TableHead>
              <TableHead class="hidden lg:table-cell">{{ t('Sample data') }}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow
              v-for="(header, idx) in preview.headers"
              :key="header"
              :class="mapping[header] ? '' : 'opacity-60'"
            >
              <TableCell class="font-mono text-xs font-medium">{{ header }}</TableCell>
              <TableCell>
                <NativeSelect
                  :model-value="mapping[header] || ''"
                  :disabled="readonly"
                  :aria-label="t('Map column “{header}”', { header })"
                  class="h-8"
                  @update:model-value="setMapping(header, String($event ?? ''))"
                >
                  <NativeSelectOption value="">{{ t('— Do not import —') }}</NativeSelectOption>
                  <NativeSelectOption v-for="f in preview.doctype_fields" :key="f.fieldname" :value="f.fieldname">
                    {{ f.label }}{{ f.required ? ' *' : '' }}
                  </NativeSelectOption>
                </NativeSelect>
              </TableCell>
              <TableCell class="hidden max-w-[160px] truncate font-mono text-xs text-muted-foreground lg:table-cell">
                {{ preview.preview_rows[0]?.[idx] ?? '' }}
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </div>

      <!-- Preview rows -->
      <details class="group">
        <summary class="text-xs text-muted-foreground cursor-pointer hover:text-foreground select-none">
          {{ t('Show first rows of the file ({n})', { n: preview.preview_rows.length }) }}
        </summary>
        <div class="mt-2 rounded-lg border text-xs">
          <Table>
            <TableHeader>
              <TableRow class="bg-muted/60">
                <TableHead v-for="h in preview.headers" :key="h" class="font-mono">{{ h }}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow v-for="(row, ri) in preview.preview_rows" :key="ri">
                <TableCell v-for="(cell, ci) in row" :key="ci" class="max-w-[140px] truncate font-mono text-muted-foreground">
                  {{ cell }}
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>
      </details>
    </template>
  </div>
</template>
