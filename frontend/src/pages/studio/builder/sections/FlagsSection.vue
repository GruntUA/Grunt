<script setup lang="ts">
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'

const { field, updateField } = usePropertyEditor()
</script>

<template>
  <Divider class="!mb-3" />
  <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Flags</p>
  <div class="flex flex-col gap-3 mb-4">
    <div class="flex items-center gap-2">
      <Checkbox binary :model-value="!!field.required" @update:model-value="updateField('required', $event)" />
      <label class="text-sm font-medium">Required</label>
    </div>
    <div class="flex items-center gap-2">
      <Checkbox binary :model-value="!!field.hidden" @update:model-value="updateField('hidden', $event)" />
      <label class="text-sm font-medium">Hidden</label>
    </div>
    <div class="flex items-center gap-2">
      <Checkbox binary :model-value="!!field.read_only" @update:model-value="updateField('read_only', $event)" />
      <label class="text-sm font-medium">Read Only</label>
    </div>
    <div class="flex items-center gap-2">
      <Checkbox binary :model-value="!!field.bold" @update:model-value="updateField('bold', $event)" />
      <label class="text-sm font-medium">Bold</label>
    </div>
    <div class="flex items-center gap-2">
      <Checkbox binary :model-value="!!field.unique" @update:model-value="updateField('unique', $event)" />
      <label class="text-sm font-medium">Unique</label>
    </div>
    <div class="flex items-center gap-2">
      <Checkbox binary :model-value="!!field.index" :disabled="!!field.unique" @update:model-value="updateField('index', $event)" />
      <label class="text-sm font-medium" :class="{ 'text-muted-foreground': !!field.unique }">Index</label>
    </div>
  </div>
</template>
