<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useWidgetPropertyEditor } from '@/core/composables/useWidgetPropertyEditor'

const { t } = useI18n()
const { widget, updateWidget } = useWidgetPropertyEditor()

const COLS = computed(() => [
  { value: 1, label: '1/4' },
  { value: 2, label: '1/2' },
  { value: 3, label: '3/4' },
  { value: 4, label: t('Full') },
])
</script>

<template>
  <div class="space-y-1">
    <label class="font-medium text-muted-foreground uppercase tracking-wide">{{ t('Width') }}</label>
    <div class="grid grid-cols-4 gap-1">
      <button
        v-for="c in COLS" :key="c.value"
        :class="[
          'py-1.5 rounded-md border transition-colors',
          widget.cols === c.value ? 'bg-primary text-primary-foreground border-primary' : 'hover:bg-muted',
        ]"
        @click="updateWidget('cols', c.value)"
      >{{ c.label }}</button>
    </div>
  </div>
</template>
