<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useBuilderStore } from '@/stores/builder'
import { metaApi } from '@/core/api/meta'
import type { DocField, DocType } from '@/types'
import BuilderCanvas from '../BuilderCanvas.vue'
import WebFormFieldPalette from './WebFormFieldPalette.vue'
import WebFormFieldPropertiesPanel from './WebFormFieldPropertiesPanel.vue'

const props = defineProps<{
  // The WebForm DocType's own meta (unused here — see note below).
  doctype: DocType
  // The WebForm *document* being edited: { doctype: "<target dt name>", fields: WebFormField[], ... }
  modelValue: Record<string, any>
}>()

const emit = defineEmits<{
  'update:modelValue': [value: Record<string, any>]
}>()

// `doctype` (the prop above) is the meta of *this* document's own DocType —
// i.e. WebForm itself, the same way DesignerTab.vue gets DocType's meta when
// editing a DocType. What the canvas needs to edit is the *target* DocType
// named in `modelValue.doctype` (e.g. "CitizenAppeal"), fetched separately.
const builder = useBuilderStore()
const ready = ref(false)
const loading = ref(false)
const loadError = ref<string | null>(null)
const targetFieldsByName = ref<Record<string, DocField>>({})

const LAYOUT_TYPES = new Set(['Tab', 'Section', 'Column'])

function buildMergedFields(targetFields: DocField[], rows: Record<string, any>[]): DocField[] {
  const targetByName = Object.fromEntries(targetFields.map((f) => [f.fieldname, f]))
  const merged: DocField[] = []
  for (const row of rows) {
    if (LAYOUT_TYPES.has(row.fieldtype)) {
      merged.push({
        fieldname: row.fieldname,
        label: row.label || '',
        fieldtype: row.fieldtype,
        collapsible: !!row.collapsible,
      })
      continue
    }
    const target = targetByName[row.fieldname]
    if (!target) continue // field removed from the target DocType since being added here
    merged.push({
      ...target,
      label: row.label || target.label,
      required: !!row.required || !!target.required,
      hidden: !!row.hidden,
      description: row.description || target.description,
    })
  }
  return merged
}

function flattenToRows(fields: DocField[]): Record<string, any>[] {
  return fields.map((f) => {
    if (LAYOUT_TYPES.has(f.fieldtype)) {
      return {
        fieldname: f.fieldname,
        fieldtype: f.fieldtype,
        label: f.label || '',
        collapsible: !!f.collapsible,
      }
    }
    const target = targetFieldsByName.value[f.fieldname]
    return {
      fieldname: f.fieldname,
      fieldtype: '',
      // Only persist an override when it actually diverges from the target
      // — an un-touched field should keep tracking the target's own label
      // if that's renamed later, rather than freezing today's value.
      label: target && f.label !== target.label ? f.label : '',
      required: !!f.required && !target?.required,
      hidden: !!f.hidden,
      description: target && f.description !== target.description ? f.description || '' : '',
    }
  })
}

async function load() {
  const targetDoctype = props.modelValue.doctype
  if (!targetDoctype) {
    targetFieldsByName.value = {}
    builder.doctype = { fields: [] } as unknown as DocType
    ready.value = true
    return
  }

  loading.value = true
  loadError.value = null
  try {
    const targetMeta = await metaApi.get(targetDoctype)
    targetFieldsByName.value = Object.fromEntries(targetMeta.fields.map((f) => [f.fieldname, f]))
    const merged = buildMergedFields(targetMeta.fields, props.modelValue.fields ?? [])
    builder.doctype = { fields: merged } as unknown as DocType
  } catch {
    loadError.value = 'Не вдалося завантажити поля обраного DocType'
  } finally {
    loading.value = false
    ready.value = true
  }
}

// Mirrors DesignerTab.vue's contract: this tab is unmounted whenever it
// isn't active, so it re-seeds from the live document on every visit — a
// single outward mirror (builder.doctype -> modelValue) is enough while
// mounted, since the designer is the only editor touching `fields` then.
watch(
  () => builder.doctype,
  (newVal) => {
    if (!ready.value || !newVal) return
    emit('update:modelValue', { ...props.modelValue, fields: flattenToRows(newVal.fields ?? []) })
  },
  { deep: true, flush: 'sync' },
)

onMounted(load)
</script>

<template>
  <div class="flex flex-col h-[75vh] min-h-[30rem] overflow-hidden -mx-5 -mb-5 border-t border-border bg-background">
    <div v-if="!modelValue.doctype" class="flex-1 flex items-center justify-center text-muted-foreground">
      Спочатку виберіть DocType на вкладці вище
    </div>
    <div v-else-if="loading" class="flex-1 flex items-center justify-center text-muted-foreground">
      Завантаження…
    </div>
    <div v-else-if="loadError" class="flex-1 flex items-center justify-center text-destructive">
      {{ loadError }}
    </div>
    <div v-else class="flex flex-1 overflow-hidden">
      <div class="w-60 shrink-0 border-r bg-card/50 overflow-y-auto">
        <WebFormFieldPalette :target-fields="Object.values(targetFieldsByName)" />
      </div>
      <div class="flex-1 overflow-hidden bg-muted/5 flex flex-col">
        <BuilderCanvas class="flex-1" />
      </div>
      <div class="w-72 shrink-0 border-l bg-card/50 overflow-y-auto">
        <WebFormFieldPropertiesPanel />
      </div>
    </div>
  </div>
</template>

<style scoped>
:deep(.builder-canvas) {
  padding: 1.5rem;
}
</style>
