<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { DocField, DocType } from '@/types'
import { metaApi } from '@/core/api'
import FieldRenderer from '@/core/renderer/FieldRenderer.vue'
import { getLayoutTypeSet } from '@/core/fieldRegistry'
import { Spinner } from '@/components/ui/spinner'

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
  doc?: Record<string, unknown>
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const LAYOUT_TYPES = getLayoutTypeSet()
const specDoctype = ref<DocType | null>(null)
const loading = ref(false)

// field.options = name of field in parent doc that holds the target DocType name
// Same pattern as DynamicLink
const targetDoctypeName = computed<string | null>(() => {
  if (!props.doc || !props.field.options) return null
  return (props.doc[props.field.options] as string) || null
})

watch(
  targetDoctypeName,
  async (name) => {
    if (!name) {
      specDoctype.value = null
      return
    }
    loading.value = true
    try {
      specDoctype.value = await metaApi.get(name)
    } catch {
      specDoctype.value = null
    } finally {
      loading.value = false
    }
  },
  { immediate: true },
)

const specFields = computed(() =>
  (specDoctype.value?.fields ?? []).filter((f) => !LAYOUT_TYPES.has(f.fieldtype) && !f.hidden),
)

const formValues = computed<Record<string, unknown>>(
  () => ((props.modelValue as Record<string, unknown>) ?? {}),
)

function update(fieldname: string, val: unknown) {
  emit('update:modelValue', { ...formValues.value, [fieldname]: val })
}
</script>

<template>
  <div v-if="loading" class="flex items-center gap-2 py-2 text-muted-foreground">
    <Spinner class="!size-4" />
    <span>Завантаження специфікації…</span>
  </div>

  <div v-else-if="specDoctype" class="flex flex-col gap-3">
    <FieldRenderer
      v-for="f in specFields"
      :key="f.fieldname"
      :field="f"
      :model-value="formValues[f.fieldname]"
      :disabled="disabled"
      :doc-values="formValues"
      @update:model-value="update(f.fieldname, $event)"
    />
  </div>

  <div v-else-if="targetDoctypeName === null" class="py-2 text-muted-foreground italic">
    Оберіть тип обладнання для відображення специфічних полів
  </div>
</template>
