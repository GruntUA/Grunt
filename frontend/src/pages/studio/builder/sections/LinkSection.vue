<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref, onMounted, useId } from 'vue'
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { metaApi } from '@/core/api'
import type { DocTypeSummary } from '@/types'
import DocTypeCombobox from '@/components/DocTypeCombobox.vue'
import { Separator } from '@/components/ui/separator'
import { Textarea } from '@/components/ui/textarea'
import { Field, FieldDescription, FieldGroup, FieldLabel, FieldLegend, FieldSet } from '@/components/ui/field'

const { t } = useI18n()

const { field, updateField } = usePropertyEditor()
const id = useId()
const doctypeList = ref<DocTypeSummary[]>([])

onMounted(async () => {
  try { doctypeList.value = await metaApi.list() } catch {}
})
</script>

<template>
  <Separator class="!mb-3" />
  <FieldSet class="mb-4">
    <FieldLegend variant="label">{{ t('Linked DocType') }}</FieldLegend>
    <FieldGroup class="gap-3">
      <DocTypeCombobox
        :model-value="field.options ?? ''"
        :options="doctypeList.map(d => d.name)"
        class="w-full"
        @update:model-value="updateField('options', $event)"
      />

      <Field v-if="field.options">
        <FieldLabel :for="`${id}-link-filters`">{{ t('Link Filters') }}</FieldLabel>
        <Textarea
          :id="`${id}-link-filters`"
          :model-value="field.link_filters ?? ''"
          rows="2"
          :placeholder="`{&quot;status&quot;: &quot;Active&quot;} ${t('or')} eval: {&quot;company&quot;: doc.company}`"
          class="font-mono"
          @update:model-value="(v: string | number) => updateField('link_filters', String(v).trim() || null)"
        />
        <FieldDescription>{{ t('JSON object or') }} <code class="bg-muted px-1 rounded">eval: {"field": doc.field}</code></FieldDescription>
      </Field>
    </FieldGroup>
  </FieldSet>
</template>
