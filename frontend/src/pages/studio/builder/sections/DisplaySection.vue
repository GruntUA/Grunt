<script setup lang="ts">
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'

const { field, updateField } = usePropertyEditor()
</script>

<template>
  <Separator class="mb-3" />
  <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Display</p>
  <div class="flex flex-col gap-2 mb-4">
    <div class="flex items-center gap-2">
      <Checkbox :model-value="!!field.in_list_view" @update:model-value="updateField('in_list_view', $event)" />
      <Label class="text-sm">In List View</Label>
    </div>
    <div class="flex items-center gap-2">
      <Checkbox :model-value="!!field.in_filter" @update:model-value="updateField('in_filter', $event)" />
      <Label class="text-sm">In Filter</Label>
    </div>
    <div class="flex items-center gap-2">
      <Checkbox :model-value="!!field.in_quick_entry" @update:model-value="updateField('in_quick_entry', $event)" />
      <Label class="text-sm">In Quick Entry</Label>
    </div>
  </div>
</template>
