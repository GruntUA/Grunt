<script setup lang="ts">
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'

const { field, updateField } = usePropertyEditor()
</script>

<template>
  <Separator class="mb-3" />
  <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Range</p>
  <div class="flex gap-2 mb-4">
    <div class="flex-1 space-y-1.5">
      <Label class="text-sm">Min</Label>
      <Input
        :model-value="String(field.min_value ?? '')"
        type="number"
        @update:model-value="updateField('min_value', $event ? Number($event) : undefined)"
      />
    </div>
    <div class="flex-1 space-y-1.5">
      <Label class="text-sm">Max</Label>
      <Input
        :model-value="String(field.max_value ?? '')"
        type="number"
        @update:model-value="updateField('max_value', $event ? Number($event) : undefined)"
      />
    </div>
  </div>
</template>
