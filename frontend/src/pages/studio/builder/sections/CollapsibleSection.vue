<script setup lang="ts">
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'

const { field, updateField } = usePropertyEditor()
</script>

<template>
  <div class="mb-4">
    <div class="flex items-center gap-2">
      <Checkbox :model-value="!!field.collapsible" @update:model-value="updateField('collapsible', $event)" />
      <label class="text-sm font-medium">Collapsible</label>
    </div>
  </div>
</template>
