<script setup lang="ts">
import { computed } from 'vue'
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Checkbox } from '@/components/ui/checkbox'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'

const { field, updateField } = usePropertyEditor()

const isDateField = computed(() => field.value.fieldtype === 'Date' || field.value.fieldtype === 'Datetime')
</script>

<template>
  <Separator class="!mb-3" />
  <p class="font-semibold text-muted-foreground uppercase tracking-wide mb-3">Display</p>
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
    <div v-if="field.in_quick_filter && isDateField" class="flex flex-col gap-1.5 pl-6">
      <label class="font-medium">Quick Filter By</label>
      <Select :model-value="field.quick_filter_mode ?? 'date'" @update:model-value="updateField('quick_filter_mode', $event === 'year' ? 'year' : null)">
        <SelectTrigger class="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="date">Date</SelectItem>
          <SelectItem value="year">Year</SelectItem>
        </SelectContent>
      </Select>
    </div>
    <div class="flex items-center gap-2">
      <Checkbox :model-value="!!field.in_quick_entry" @update:model-value="updateField('in_quick_entry', $event)" />
      <label class="font-medium">In Quick Entry</label>
    </div>
    <div class="flex items-center gap-2">
      <Checkbox :model-value="!!field.in_preview" @update:model-value="updateField('in_preview', $event)" />
      <label class="font-medium">In Preview</label>
    </div>
  </div>
</template>
