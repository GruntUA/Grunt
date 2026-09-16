<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Textarea } from '@/components/ui/textarea'
import { useWidgetPropertyEditor } from '@/core/composables/useWidgetPropertyEditor'

const { t } = useI18n()
const { widget, updateWidget } = useWidgetPropertyEditor()
</script>

<template>
  <div class="flex flex-col gap-1.5 mb-4">
    <label class="font-medium">{{ t('Content (HTML/text)') }}</label>
    <Textarea
      :model-value="widget.content ?? ''"
      rows="5"
      class="w-full !font-mono !text-sm"
      @update:model-value="(v: string | number) => updateWidget('content', String(v))"
    />
  </div>
</template>
