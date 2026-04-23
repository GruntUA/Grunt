<script setup lang="ts">
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { getLayoutTypeSet } from '@/core/fieldRegistry'

const { field, updateField } = usePropertyEditor()
const LAYOUT_TYPES = getLayoutTypeSet()
</script>

<template>
  <div class="flex flex-col gap-3 mb-4">
    <div class="flex flex-col gap-1.5">
      <label class="text-sm font-medium">Label</label>
      <InputText :model-value="field.label" class="w-full" @update:model-value="updateField('label', $event)" />
    </div>
    <div class="flex flex-col gap-1.5">
      <label class="text-sm font-medium text-muted-foreground">Fieldname</label>
      <InputText
        :model-value="field.fieldname"
        :disabled="LAYOUT_TYPES.has(field.fieldtype)"
        class="w-full"
        @update:model-value="updateField('fieldname', $event)"
      />
    </div>
  </div>
</template>
