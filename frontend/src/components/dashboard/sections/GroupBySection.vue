<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Input } from '@/components/ui/input'
import { useWidgetPropertyEditor } from '@/core/composables/useWidgetPropertyEditor'
import { isReportSourced } from './widgetHelpers'

const { t } = useI18n()
const { widget, updateWidget } = useWidgetPropertyEditor()
</script>

<template>
  <div v-if="!isReportSourced(widget)" class="flex flex-col gap-1.5 mb-4">
    <label class="font-medium">{{ t('Group by') }}</label>
    <Input
      :model-value="widget.group_by ?? ''"
      placeholder="fieldname"
      class="w-full"
      @update:model-value="updateWidget('group_by', $event)"
    />
  </div>
</template>
