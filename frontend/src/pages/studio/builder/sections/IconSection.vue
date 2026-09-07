<script setup lang="ts">
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import IconPicker from '@/components/fields/Icon/Icon.vue'
import { Separator } from '@/components/ui/separator'

const { field, updateField } = usePropertyEditor()
</script>

<template>
  <Separator class="!mb-3" />
  <p class="font-semibold text-muted-foreground uppercase tracking-wide mb-3">Icon</p>
  <div class="mb-4">
    <IconPicker
      :field="field"
      :model-value="field.icon ?? null"
      @update:model-value="updateField('icon', $event ?? undefined)"
    />
  </div>
</template>
