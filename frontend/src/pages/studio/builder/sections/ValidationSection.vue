<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref, onMounted, computed, useId } from 'vue'
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { metaApi, type ValidatorInfo } from '@/core/api/meta'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Field, FieldGroup, FieldLabel, FieldLegend, FieldSet } from '@/components/ui/field'

const { t } = useI18n()

const { field, updateField } = usePropertyEditor()
const id = useId()

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
    { value: '__none__', label: t('— not set —') },
    ...applicable.map(v => ({ value: v.name, label: v.label })),
  ]
})

const hasValidators = computed(() => validatorOptions.value.length > 1)
</script>

<template>
  <Separator class="!mb-3" />
  <FieldSet class="mb-4">
    <FieldLegend variant="label">{{ t('Validation') }}</FieldLegend>
    <FieldGroup class="gap-3">
      <Field v-if="['Text', 'LongText'].includes(field.fieldtype)">
        <FieldLabel :for="`${id}-max-length`">{{ t('Max Length') }}</FieldLabel>
        <Input
          :id="`${id}-max-length`"
          type="number"
          :model-value="field.max_length ?? ''"
          placeholder="255"
          @update:model-value="(v: string | number) => updateField('max_length', v === '' ? undefined : Number(v))"
        />
      </Field>

      <Field v-if="hasValidators">
        <FieldLabel :for="`${id}-validator`">{{ t('Validator') }}</FieldLabel>
        <Select :model-value="field.validator || '__none__'" @update:model-value="updateField('validator', $event === '__none__' ? undefined : $event)">
          <SelectTrigger :id="`${id}-validator`" class="w-full">
            <SelectValue :placeholder="t('— not set —')" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="opt in validatorOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
          </SelectContent>
        </Select>
      </Field>

      <Field>
        <FieldLabel :for="`${id}-regex`">{{ t('Regex') }}</FieldLabel>
        <Input
          :id="`${id}-regex`"
          :model-value="field.regex ?? ''"
          placeholder="^[A-Z].*"
          @update:model-value="updateField('regex', $event || undefined)"
        />
      </Field>
    </FieldGroup>
  </FieldSet>
</template>
