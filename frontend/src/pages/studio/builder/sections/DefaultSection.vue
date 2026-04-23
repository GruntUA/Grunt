<script setup lang="ts">
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'

const { field, updateField } = usePropertyEditor()
</script>

<template>
  <Divider class="!mb-3" />
  <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Default</p>
  <div class="mb-4">
    <InputText
      :model-value="String(field.default ?? '')"
      placeholder="Default value"
      class="w-full"
      @update:model-value="updateField('default', $event || undefined)"
    />
  </div>
</template>
