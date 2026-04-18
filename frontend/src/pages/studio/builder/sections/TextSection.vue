<script setup lang="ts">
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'

const { field, updateField } = usePropertyEditor()
</script>

<template>
  <Separator class="mb-3" />
  <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Text</p>
  <div class="flex flex-col gap-3 mb-4">
    <div class="space-y-1.5">
      <Label class="text-sm">Description</Label>
      <Input :model-value="field.description ?? ''" @update:model-value="updateField('description', $event || undefined)" />
    </div>
    <div class="space-y-1.5">
      <Label class="text-sm">Placeholder</Label>
      <Input :model-value="field.placeholder ?? ''" @update:model-value="updateField('placeholder', $event || undefined)" />
    </div>
    <div class="space-y-1.5">
      <Label class="text-sm">Depends On</Label>
      <Input :model-value="field.depends_on ?? ''" placeholder="eval: doc.status == 'Active'" @update:model-value="updateField('depends_on', $event || undefined)" />
    </div>
    <div class="space-y-1.5">
      <Label class="text-sm">Mandatory Depends On</Label>
      <Input :model-value="field.mandatory_depends_on ?? ''" placeholder="eval: doc.type == 'Full'" @update:model-value="updateField('mandatory_depends_on', $event || undefined)" />
    </div>
  </div>
</template>
