<script setup lang="ts">
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { getLayoutTypeSet } from '@/core/fieldRegistry'

const { field, updateField } = usePropertyEditor()
const LAYOUT_TYPES = getLayoutTypeSet()
</script>

<template>
  <div class="flex flex-col gap-3 mb-4">
    <div class="space-y-1.5">
      <Label class="text-sm">Label</Label>
      <Input :model-value="field.label" @update:model-value="updateField('label', $event)" />
    </div>
    <div class="space-y-1.5">
      <Label class="text-sm text-muted-foreground">Fieldname</Label>
      <Input
        :model-value="field.fieldname"
        :disabled="LAYOUT_TYPES.has(field.fieldtype)"
        @update:model-value="updateField('fieldname', $event)"
      />
    </div>
  </div>
</template>
