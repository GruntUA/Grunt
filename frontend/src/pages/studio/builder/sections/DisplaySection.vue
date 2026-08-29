<script setup lang="ts">
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Checkbox } from '@/components/ui/checkbox'
import { Separator } from '@/components/ui/separator'

const { field, updateField } = usePropertyEditor()
</script>

<template>
  <Separator class="!mb-3" />
  <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Display</p>
  <div class="flex flex-col gap-3 mb-4">
    <div class="flex items-center gap-2">
      <Checkbox :model-value="!!field.in_list_view" @update:model-value="updateField('in_list_view', $event)" />
      <label class="font-medium">In List View</label>
    </div>
    <div class="flex items-center gap-2">
      <Checkbox :model-value="!!field.in_filter" @update:model-value="updateField('in_filter', $event)" />
      <label class="font-medium">In Filter</label>
    </div>
    <div class="flex items-center gap-2">
      <Checkbox :model-value="!!field.in_quick_filter" @update:model-value="updateField('in_quick_filter', $event)" />
      <label class="font-medium">In Quick Filter</label>
    </div>
    <div class="flex items-center gap-2">
      <Checkbox :model-value="!!field.in_quick_entry" @update:model-value="updateField('in_quick_entry', $event)" />
      <label class="font-medium">In Quick Entry</label>
    </div>
  </div>
</template>
