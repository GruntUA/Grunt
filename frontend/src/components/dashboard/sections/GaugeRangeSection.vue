<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import { useWidgetPropertyEditor } from '@/core/composables/useWidgetPropertyEditor'

const { t } = useI18n()
const { widget, updateWidget } = useWidgetPropertyEditor()
</script>

<template>
  <Separator class="!mb-3" />
  <p class="font-semibold text-muted-foreground uppercase tracking-wide mb-3">{{ t('Range') }}</p>
  <div class="flex gap-2 mb-4">
    <div class="flex-1 flex flex-col gap-1.5">
      <label class="font-medium">{{ t('Min') }}</label>
      <Input
        type="number"
        :model-value="widget.min_value ?? ''"
        class="w-full"
        @update:model-value="(v: string | number) => updateWidget('min_value', v === '' ? null : Number(v))"
      />
    </div>
    <div class="flex-1 flex flex-col gap-1.5">
      <label class="font-medium">{{ t('Max') }}</label>
      <Input
        type="number"
        :model-value="widget.max_value ?? ''"
        class="w-full"
        @update:model-value="(v: string | number) => updateWidget('max_value', v === '' ? null : Number(v))"
      />
    </div>
  </div>
</template>
