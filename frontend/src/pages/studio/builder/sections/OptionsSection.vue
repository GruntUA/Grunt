<script setup lang="ts">
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Separator } from '@/components/ui/separator'
import { Textarea } from '@/components/ui/textarea'

const { field, updateField } = usePropertyEditor()
</script>

<template>
  <Separator class="!mb-3" />
  <p class="font-semibold text-muted-foreground uppercase tracking-wide mb-3">Options</p>
  <div class="mb-4">
    <Textarea
      :model-value="field.options ?? ''"
      rows="5"
      placeholder="Кожна опція з нового рядка"
      class="w-full !text-sm"
      @update:model-value="(v: string | number) => updateField('options', String(v))"
    />
  </div>
</template>
