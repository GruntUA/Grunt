<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Checkbox } from '@/components/ui/checkbox'
import { Separator } from '@/components/ui/separator'

const { t } = useI18n()

const { field, updateField } = usePropertyEditor()

function toggle() {
  updateField('show_connections', !field.value.show_connections)
}
</script>

<template>
  <Separator class="!mb-3" />
  <p class="font-semibold text-muted-foreground uppercase tracking-wide mb-3">{{ t('Tab') }}</p>
  <div class="mb-4">
    <div class="flex items-start gap-2">
      <Checkbox
        :model-value="!!field.show_connections"
        class="mt-0.5 shrink-0"
        @update:model-value="updateField('show_connections', $event)"
      />
      <span
        class="text-sm font-medium text-foreground leading-snug cursor-pointer select-none"
        @click="toggle"
      >
        {{ t('Show the «Connections» panel in this tab') }}
      </span>
    </div>
    <p class="mt-1.5 text-muted-foreground leading-snug">
      {{ t('Linked documents (counters, «+ New») render at the top of this tab. If off everywhere, the panel shows above the form.') }}
    </p>
  </div>
</template>
