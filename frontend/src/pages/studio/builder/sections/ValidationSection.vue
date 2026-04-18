<script setup lang="ts">
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'

const { field, updateField } = usePropertyEditor()
</script>

<template>
  <Separator class="mb-3" />
  <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Validation</p>
  <div class="flex flex-col gap-3 mb-4">
    <div v-if="['Text', 'LongText'].includes(field.fieldtype)" class="space-y-1.5">
      <Label class="text-sm">Max Length</Label>
      <Input
        :model-value="String(field.max_length ?? '')"
        type="number"
        placeholder="255"
        @update:model-value="updateField('max_length', $event ? Number($event) : undefined)"
      />
    </div>
    <div class="space-y-1.5">
      <Label class="text-sm">Regex</Label>
      <Input
        :model-value="field.regex ?? ''"
        placeholder="^[A-Z].*"
        @update:model-value="updateField('regex', $event || undefined)"
      />
    </div>
  </div>
</template>
