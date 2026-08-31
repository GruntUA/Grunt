<script setup lang="ts">
import { ref, computed, inject, provide, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { BaseFieldProps, DocType } from '@/types'
import { metaApi } from '@/core/api'
import FieldRenderer from '@/core/renderer/FieldRenderer.vue'
import { FORM_ERRORS } from '@/core/renderer/formErrors'
import { getLayoutTypeSet } from '@/core/fieldRegistry'
import { Spinner } from '@/components/ui/spinner'

const props = defineProps<BaseFieldProps>()
const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const { t } = useI18n()

// Re-scope the form error map so a nested field `foo` resolves against
// `errors["<this field>.foo"]` (or deeper, if we're already nested).
const parentErrors = inject(FORM_ERRORS, null)
provide(FORM_ERRORS, {
  errors: parentErrors?.errors ?? computed<Record<string, string>>(() => ({})),
  prefix: `${parentErrors?.prefix ?? ''}${props.field.fieldname}.`,
})

const LAYOUT_TYPES = getLayoutTypeSet()
const specDoctype = ref<DocType | null>(null)
const loading = ref(false)

// field.options = name of the field in the parent doc that holds the target
// DocType name (same pattern as DynamicLink).
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
  () => (props.modelValue as Record<string, unknown>) ?? {},
)

const isDisabled = computed(() => !!props.disabled || !!props.field.read_only)

function update(fieldname: string, val: unknown) {
  emit('update:modelValue', { ...formValues.value, [fieldname]: val })
}
</script>

<template>
  <div v-if="loading" class="flex items-center gap-2 py-2 text-muted-foreground">
    <Spinner class="!size-4" />
    <span>{{ t('Loading fields…') }}</span>
  </div>

  <div v-else-if="specDoctype" class="flex flex-col gap-3">
    <FieldRenderer
      v-for="f in specFields"
      :key="f.fieldname"
      :field="f"
      :model-value="formValues[f.fieldname]"
      :disabled="isDisabled"
      :doc-values="formValues"
      @update:model-value="update(f.fieldname, $event)"
    />
  </div>

  <div v-else-if="targetDoctypeName === null" class="py-2 italic text-muted-foreground">
    {{ t('Select a type to show its fields') }}
  </div>
</template>
