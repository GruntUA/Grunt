<script setup lang="ts">
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'

const { field, updateField } = usePropertyEditor()
</script>

<template>
  <Divider class="!mb-3" />
  <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Text</p>
  <div class="flex flex-col gap-3 mb-4">
    <div class="flex flex-col gap-1.5">
      <label class="text-sm font-medium">Description</label>
      <InputText :model-value="field.description ?? ''" class="w-full" @update:model-value="updateField('description', $event || undefined)" />
    </div>
    <div class="flex flex-col gap-1.5">
      <label class="text-sm font-medium">Placeholder</label>
      <InputText :model-value="field.placeholder ?? ''" class="w-full" @update:model-value="updateField('placeholder', $event || undefined)" />
    </div>
    <div class="flex flex-col gap-1.5">
      <label class="text-sm font-medium">Depends On</label>
      <InputText :model-value="field.depends_on ?? ''" placeholder="eval: doc.status == 'Active'" class="w-full" @update:model-value="updateField('depends_on', $event || undefined)" />
    </div>
    <div class="flex flex-col gap-1.5">
      <label class="text-sm font-medium">Mandatory Depends On</label>
      <InputText :model-value="field.mandatory_depends_on ?? ''" placeholder="eval: doc.type == 'Full'" class="w-full" @update:model-value="updateField('mandatory_depends_on', $event || undefined)" />
    </div>
  </div>
</template>
