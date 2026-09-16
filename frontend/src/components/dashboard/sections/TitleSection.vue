<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Input } from '@/components/ui/input'
import { useWidgetPropertyEditor } from '@/core/composables/useWidgetPropertyEditor'

const { t } = useI18n()
const { widget, updateWidget } = useWidgetPropertyEditor()
</script>

<template>
  <div class="flex flex-col gap-1.5 mb-4">
    <label class="font-medium">{{ t('Title') }}</label>
    <Input
      :model-value="widget.title"
      :placeholder="t('Widget title')"
      class="w-full"
      @update:model-value="updateWidget('title', $event)"
    />
  </div>
</template>
