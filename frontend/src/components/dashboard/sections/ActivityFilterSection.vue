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
  <Field class="mb-4">
    <FieldLabel>
      {{ t('Filter by DocType') }} <span class="font-normal text-muted-foreground">({{ t('optional') }})</span>
    </FieldLabel>
    <DocTypeCombobox
      :model-value="widget.ref_doctype"
      :options="doctypeNames"
      :placeholder="t('— All —')"
      class="w-full"
      @update:model-value="updateWidget('ref_doctype', $event)"
    />
  </Field>
</template>
