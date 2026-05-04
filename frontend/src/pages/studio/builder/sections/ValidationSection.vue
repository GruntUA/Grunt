<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { metaApi, type ValidatorInfo } from '@/core/api/meta'

const { field, updateField } = usePropertyEditor()

const allValidators = ref<ValidatorInfo[]>([])
onMounted(async () => {
  try {
    allValidators.value = await metaApi.listValidators()
  } catch {}
})

const validatorOptions = computed(() => {
  const applicable = allValidators.value.filter(
    v => v.field_types.includes(field.value.fieldtype)
  )
  return [
    { value: '', label: '— не обрано —' },
    ...applicable.map(v => ({ value: v.name, label: v.label })),
  ]
})

const hasValidators = computed(() => validatorOptions.value.length > 1)
</script>

<template>
  <Divider class="!mb-3" />
  <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Validation</p>
  <div class="flex flex-col gap-3 mb-4">
    <div v-if="['Text', 'LongText'].includes(field.fieldtype)" class="flex flex-col gap-1.5">
      <label class="text-sm font-medium">Max Length</label>
      <InputNumber
        :model-value="field.max_length"
        placeholder="255"
        class="w-full"
        @update:model-value="updateField('max_length', $event || undefined)"
      />
    </div>

    <div v-if="hasValidators" class="flex flex-col gap-1.5">
      <label class="text-sm font-medium">Validator</label>
      <Select
        :model-value="field.validator ?? ''"
        :options="validatorOptions"
        option-label="label"
        option-value="value"
        placeholder="— не обрано —"
        class="w-full"
        @update:model-value="updateField('validator', $event || undefined)"
      />
    </div>

    <div class="flex flex-col gap-1.5">
      <label class="text-sm font-medium">Regex</label>
      <InputText
        :model-value="field.regex ?? ''"
        placeholder="^[A-Z].*"
        class="w-full"
        @update:model-value="updateField('regex', $event || undefined)"
      />
    </div>
  </div>
</template>
