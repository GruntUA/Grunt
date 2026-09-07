<script setup lang="ts">
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'

const { field, updateField } = usePropertyEditor()
</script>

<template>
  <Separator class="!mb-3" />
  <p class="font-semibold text-muted-foreground uppercase tracking-wide mb-3">Default</p>
  <div class="mb-4">
    <Input
      :model-value="String(field.default ?? '')"
      placeholder="Default value"
      class="w-full"
      @update:model-value="updateField('default', $event || undefined)"
    />
  </div>
</template>
