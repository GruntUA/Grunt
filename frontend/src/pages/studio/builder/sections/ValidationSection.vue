<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { metaApi, type ValidatorInfo } from '@/core/api/meta'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'

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
  <Separator class="!mb-3" />
  <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Validation</p>
  <div class="flex flex-col gap-3 mb-4">
    <div v-if="['Text', 'LongText'].includes(field.fieldtype)" class="flex flex-col gap-1.5">
      <label class="text-sm font-medium">Max Length</label>
      <Input
        type="number"
        :model-value="field.max_length ?? ''"
        placeholder="255"
        class="w-full"
        @update:model-value="(v: string | number) => updateField('max_length', v === '' ? undefined : Number(v))"
      />
    </div>

    <div v-if="hasValidators" class="flex flex-col gap-1.5">
      <label class="text-sm font-medium">Validator</label>
      <Select :model-value="field.validator ?? ''" @update:model-value="updateField('validator', $event || undefined)">
        <SelectTrigger class="w-full">
          <SelectValue placeholder="— не обрано —" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem v-for="opt in validatorOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
        </SelectContent>
      </Select>
    </div>

    <div class="flex flex-col gap-1.5">
      <label class="text-sm font-medium">Regex</label>
      <Input
        :model-value="field.regex ?? ''"
        placeholder="^[A-Z].*"
        class="w-full"
        @update:model-value="updateField('regex', $event || undefined)"
      />
    </div>
  </div>
</template>
