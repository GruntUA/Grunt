<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DocField } from '@/types'
import FieldRenderer from '@/core/renderer/FieldRenderer.vue'
import { Button } from '@/components/ui/button'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'

/**
 * The whole row as a form - every field of the child DocType, including those
 * the grid can't edit inline. Edits a draft; Save hands it back.
 */
const props = defineProps<{
  /** The row being edited; `null` closes the sheet. */
  row: Record<string, unknown> | null
  /** 1-based position shown in the title. */
  position: number
  fields: DocField[]
  /** Field holding a per-row sub-form (dynamic_schema_source), if any. */
  dynamicField?: DocField
  tableLabel: string
  disabled?: boolean
}>()

const emit = defineEmits<{
  close: []
  save: [row: Record<string, unknown>]
  'create-new': [doctype: string, preset: string, apply: (docname: string) => void]
}>()

const { t } = useI18n()
const draft = ref<Record<string, unknown>>({})

watch(
  () => props.row,
  (row) => {
    if (row) draft.value = { ...row }
  },
  { immediate: true },
)

function set(fieldname: string, value: unknown) {
  draft.value = { ...draft.value, [fieldname]: value }
}

// The dynamic field (e.g. WebPageBlock.settings) holds a sub-form whose fields
// depend on a sibling (dynamic_schema_key, e.g. block_type) of the row.
const dynamicField = computed(() => props.dynamicField)
const dynamicFields = computed<DocField[]>(() => {
  const f = dynamicField.value
  const variant = f?.dynamic_schema_key ? (draft.value[f.dynamic_schema_key] as string) : ''
  return (variant && f?.dynamic_schemas?.[variant]) || []
})
const dynamicValues = computed(
  () => (draft.value[dynamicField.value?.fieldname ?? ''] as Record<string, unknown>) ?? {},
)

function setDynamic(fieldname: string, value: unknown) {
  const source = dynamicField.value?.fieldname
  if (source) set(source, { ...dynamicValues.value, [fieldname]: value })
}

function onCreateNew(doctype: string, preset: string, fieldname: string) {
  emit('create-new', doctype, preset, (docname) => set(fieldname, docname))
}
</script>

<template>
  <Sheet :open="row !== null" @update:open="(open) => !open && emit('close')">
    <SheetContent class="w-full sm:max-w-lg">
      <SheetHeader>
        <SheetTitle>{{ t('Row') }} {{ position }}</SheetTitle>
        <SheetDescription>{{ tableLabel }}</SheetDescription>
      </SheetHeader>

      <div class="flex flex-1 flex-col gap-4 overflow-y-auto px-4">
        <FieldRenderer
          v-for="f in fields"
          :key="f.fieldname"
          :field="f"
          :model-value="draft[f.fieldname]"
          :disabled="disabled"
          :doc-values="draft"
          @update:model-value="set(f.fieldname, $event)"
          @create-new="onCreateNew"
        />
        <FieldRenderer
          v-for="f in dynamicFields"
          :key="`dyn-${f.fieldname}`"
          :field="f"
          :model-value="dynamicValues[f.fieldname]"
          :disabled="disabled"
          :doc-values="draft"
          @update:model-value="setDynamic(f.fieldname, $event)"
          @create-new="onCreateNew"
        />
      </div>

      <SheetFooter class="flex-row justify-end">
        <Button variant="outline" @click="emit('close')">
          {{ disabled ? t('Close') : t('Cancel') }}
        </Button>
        <Button v-if="!disabled" @click="emit('save', draft)">{{ t('Save') }}</Button>
      </SheetFooter>
    </SheetContent>
  </Sheet>
</template>
