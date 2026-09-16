<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDocTypeStore } from '@/stores/doctype'
import DocTypeCombobox from '@/components/DocTypeCombobox.vue'
import { useWidgetPropertyEditor } from '@/core/composables/useWidgetPropertyEditor'

const { t } = useI18n()
const dtStore = useDocTypeStore()
const { widget, updateWidget } = useWidgetPropertyEditor()

const doctypeNames = computed(() => dtStore.doctypes.filter(d => !d.is_child).map(d => d.name))
</script>

<template>
  <div class="flex flex-col gap-1.5 mb-4">
    <label class="font-medium">
      {{ t('Filter by DocType') }} <span class="font-normal text-muted-foreground">({{ t('optional') }})</span>
    </label>
    <DocTypeCombobox
      :model-value="widget.doctype"
      :options="doctypeNames"
      :placeholder="t('— All —')"
      class="w-full"
      @update:model-value="updateWidget('doctype', $event)"
    />
  </div>
</template>
