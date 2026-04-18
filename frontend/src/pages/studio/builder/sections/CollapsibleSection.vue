<script setup lang="ts">
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'

const { field, updateField } = usePropertyEditor()
</script>

<template>
  <div class="mb-4">
    <div class="flex items-center gap-2">
      <Checkbox :model-value="!!field.collapsible" @update:model-value="updateField('collapsible', $event)" />
      <Label class="text-sm">Collapsible</Label>
    </div>
  </div>
</template>
