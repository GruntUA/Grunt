<script setup lang="ts">
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'

const { field, updateField } = usePropertyEditor()
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
