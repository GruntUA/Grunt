<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { X } from '@lucide/vue'
import type { ActiveFilter, DocType } from '@/types'
import { useDocTypeStore } from '@/stores/doctype'
import { OP_MAP, displayOp, filtersToRaw } from '@/core/api/docs'
import { useWidgetPropertyEditor } from '@/core/composables/useWidgetPropertyEditor'
import FilterBar from '@/components/views/FilterBar.vue'
import { isReportSourced } from './widgetHelpers'

const { t } = useI18n()
const dtStore = useDocTypeStore()
const { widget, updateWidget } = useWidgetPropertyEditor()

const dt = ref<DocType | null>(null)
watch(() => widget.value.ref_doctype, async (name) => {
  dt.value = name ? await dtStore.get(name).catch(() => null) : null
}, { immediate: true })

const BACKEND_OPS = new Set(Object.values(OP_MAP))

const raw = computed<Record<string, unknown>>(() => {
  const f: unknown = widget.value.filters
  if (typeof f === 'string') {
    try { return JSON.parse(f || '{}') } catch { return {} }
  }
  return (f as Record<string, unknown>) ?? {}
})

/**
 * Split the widget's `{field__op: value}` dict: what the filter bar can edit, and
 * the rest (`@today-7d` tokens, unknown fields/operators) kept verbatim.
 */
const split = computed(() => {
  const editable: ActiveFilter[] = []
  const kept: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(raw.value)) {
    const [fieldname, backendOp = 'eq'] = key.split('__')
    const field = dt.value?.fields.find(f => f.fieldname === fieldname)
    const list = Array.isArray(value) && (backendOp === 'in' || backendOp === 'nin')
    const scalar = typeof value === 'string' || typeof value === 'number'
    if (!field || !(scalar || list) || !BACKEND_OPS.has(backendOp) || String(value).startsWith('@')) {
      kept[key] = value
      continue
    }
    const text = list ? (value as unknown[]).join(',') : String(value)
    editable.push({
      fieldname, label: field.label, fieldtype: field.fieldtype,
      op: displayOp(backendOp, text), value: text,
    })
  }
  return { editable, kept }
})

function save(filters: Record<string, unknown>) {
  updateWidget('filters', Object.keys(filters).length ? filters : null)
}

function onChange(active: ActiveFilter[]) {
  save({ ...split.value.kept, ...filtersToRaw(active) })
}

function removeKept(key: string) {
  const { [key]: _, ...rest } = raw.value
  save(rest)
}
</script>

<template>
  <div v-if="!isReportSourced(widget) && dt" class="flex flex-col gap-1.5 mb-4">
    <label class="font-medium">{{ t('Filters') }}</label>
    <FilterBar
      :key="`${widget.id}:${dt.name}`"
      :fields="dt.fields"
      :initial-filters="split.editable"
      all-fields
      @change="onChange"
    />
    <div v-for="(value, key) in split.kept" :key="key" class="flex items-center gap-1 text-muted-foreground">
      <code class="truncate">{{ key }} = {{ JSON.stringify(value) }}</code>
      <button type="button" class="shrink-0 hover:text-destructive" :title="t('Delete')" @click="removeKept(String(key))">
        <X class="size-3" />
      </button>
    </div>
  </div>
</template>
