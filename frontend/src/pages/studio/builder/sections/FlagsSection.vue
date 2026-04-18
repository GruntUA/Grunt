<script setup lang="ts">
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'

const { field, updateField } = usePropertyEditor()
</script>

<template>
  <Separator class="mb-3" />
  <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Flags</p>
  <div class="flex flex-col gap-2 mb-4">
    <div class="flex items-center gap-2">
      <Checkbox :model-value="!!field.required" @update:model-value="updateField('required', $event)" />
      <Label class="text-sm">Required</Label>
    </div>
    <div class="flex items-center gap-2">
      <Checkbox :model-value="!!field.hidden" @update:model-value="updateField('hidden', $event)" />
      <Label class="text-sm">Hidden</Label>
    </div>
    <div class="flex items-center gap-2">
      <Checkbox :model-value="!!field.read_only" @update:model-value="updateField('read_only', $event)" />
      <Label class="text-sm">Read Only</Label>
    </div>
    <div class="flex items-center gap-2">
      <Checkbox :model-value="!!field.bold" @update:model-value="updateField('bold', $event)" />
      <Label class="text-sm">Bold</Label>
    </div>
    <div class="flex items-center gap-2">
      <Checkbox :model-value="!!field.unique" @update:model-value="updateField('unique', $event)" />
      <Label class="text-sm">Unique</Label>
    </div>
    <div class="flex items-center gap-2">
      <Checkbox :model-value="!!field.index" :disabled="!!field.unique" @update:model-value="updateField('index', $event)" />
      <Label class="text-sm" :class="{ 'text-muted-foreground': !!field.unique }">Index</Label>
    </div>
  </div>
</template>
