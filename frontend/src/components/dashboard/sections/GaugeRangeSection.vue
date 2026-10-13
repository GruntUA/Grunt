<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useId } from 'vue'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import { Field, FieldLabel } from '@/components/ui/field'
import { useWidgetPropertyEditor } from '@/core/composables/useWidgetPropertyEditor'

const { t } = useI18n()
const id = useId()
const { widget, updateWidget } = useWidgetPropertyEditor()
</script>

<template>
  <Separator class="!mb-3" />
  <p class="font-semibold text-muted-foreground uppercase tracking-wide mb-3">{{ t('Range') }}</p>
  <div class="flex gap-2 mb-4">
    <Field class="flex-1">
      <FieldLabel :for="`${id}-1`">{{ t('Min') }}</FieldLabel>
      <Input
        :id="`${id}-1`"
        type="number"
        :model-value="widget.min_value ?? ''"
        class="w-full"
        @update:model-value="(v: string | number) => updateWidget('min_value', v === '' ? null : Number(v))"
      />
    </Field>
    <Field class="flex-1">
      <FieldLabel :for="`${id}-2`">{{ t('Max') }}</FieldLabel>
      <Input
        :id="`${id}-2`"
        type="number"
        :model-value="widget.max_value ?? ''"
        class="w-full"
        @update:model-value="(v: string | number) => updateWidget('max_value', v === '' ? null : Number(v))"
      />
    </Field>
  </div>
</template>
