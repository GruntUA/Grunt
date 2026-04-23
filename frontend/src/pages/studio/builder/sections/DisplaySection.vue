<script setup lang="ts">
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'

const { field, updateField } = usePropertyEditor()
</script>

<template>
  <Divider class="!mb-3" />
  <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Display</p>
  <div class="flex flex-col gap-3 mb-4">
    <div class="flex items-center gap-2">
      <Checkbox binary :model-value="!!field.in_list_view" @update:model-value="updateField('in_list_view', $event)" />
      <label class="text-sm font-medium">In List View</label>
    </div>
    <div class="flex items-center gap-2">
      <Checkbox binary :model-value="!!field.in_filter" @update:model-value="updateField('in_filter', $event)" />
      <label class="text-sm font-medium">In Filter</label>
    </div>
    <div class="flex items-center gap-2">
      <Checkbox binary :model-value="!!field.in_quick_entry" @update:model-value="updateField('in_quick_entry', $event)" />
      <label class="text-sm font-medium">In Quick Entry</label>
    </div>
  </div>
</template>
