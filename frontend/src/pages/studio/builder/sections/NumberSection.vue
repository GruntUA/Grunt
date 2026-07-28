<script setup lang="ts">
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'

const { field, updateField } = usePropertyEditor()
</script>

<template>
  <Separator class="!mb-3" />
  <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Range</p>
  <div class="flex gap-2 mb-4">
    <div class="flex-1 flex flex-col gap-1.5">
      <label class="text-sm font-medium">Min</label>
      <Input
        type="number"
        :model-value="field.min_value ?? ''"
        class="w-full"
        @update:model-value="(v: string | number) => updateField('min_value', v === '' ? undefined : Number(v))"
      />
    </div>
    <div class="flex-1 flex flex-col gap-1.5">
      <label class="text-sm font-medium">Max</label>
      <Input
        type="number"
        :model-value="field.max_value ?? ''"
        class="w-full"
        @update:model-value="(v: string | number) => updateField('max_value', v === '' ? undefined : Number(v))"
      />
    </div>
  </div>
</template>
