<script setup lang="ts">
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'

const { field, updateField } = usePropertyEditor()
</script>

<template>
  <Divider class="!mb-3" />
  <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Options</p>
  <div class="mb-4">
    <Textarea
      :model-value="field.options ?? ''"
      rows="5"
      placeholder="Кожна опція з нового рядка"
      class="w-full !text-sm"
      autoResize
      @input="updateField('options', ($event.target as HTMLTextAreaElement).value)"
    />
  </div>
</template>
