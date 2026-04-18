<script setup lang="ts">
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Separator } from '@/components/ui/separator'

const { field, updateField } = usePropertyEditor()
</script>

<template>
  <Separator class="mb-3" />
  <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Options</p>
  <div class="mb-4">
    <textarea
      :value="field.options ?? ''"
      rows="5"
      placeholder="Each option on a new line"
      class="w-full text-sm border border-input rounded-md px-2 py-1.5 bg-background focus:outline-none focus:ring-1 focus:ring-ring"
      @input="updateField('options', ($event.target as HTMLTextAreaElement).value)"
    />
  </div>
</template>
