<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Input } from '@/components/ui/input'
import { useWidgetPropertyEditor } from '@/core/composables/useWidgetPropertyEditor'

const { t } = useI18n()
const { widget, updateWidget } = useWidgetPropertyEditor()

const label = computed(() => widget.value.widget_type === 'clock' ? t('Note') : t('Subtitle'))
</script>

<template>
  <div class="flex flex-col gap-1.5 mb-4">
    <label class="font-medium">{{ label }}</label>
    <Input
      :model-value="widget.description ?? ''"
      class="w-full"
      @update:model-value="updateWidget('description', $event)"
    />
  </div>
</template>
