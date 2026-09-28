<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref, onMounted } from 'vue'
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { metaApi } from '@/core/api'
import type { DocTypeSummary } from '@/types'
import DocTypeCombobox from '@/components/DocTypeCombobox.vue'
import { Separator } from '@/components/ui/separator'
import { Textarea } from '@/components/ui/textarea'

const { t } = useI18n()

const { field, updateField } = usePropertyEditor()
const doctypeList = ref<DocTypeSummary[]>([])

onMounted(async () => {
  try { doctypeList.value = await metaApi.list() } catch {}
})
</script>

<template>
  <Separator class="!mb-3" />
  <p class="font-semibold text-muted-foreground uppercase tracking-wide mb-3">Linked DocType</p>
  <div class="mb-4">
    <DocTypeCombobox
      :model-value="field.options ?? ''"
      :options="doctypeList.map(d => d.name)"
      class="w-full"
      @update:model-value="updateField('options', $event)"
    />
  </div>

  <div v-if="field.options" class="mb-4 flex flex-col gap-1.5">
    <label class="font-medium">Link Filters</label>
    <Textarea
      :model-value="field.link_filters ?? ''"
      rows="2"
      :placeholder="`{&quot;status&quot;: &quot;Active&quot;} ${t('or')} eval: {&quot;company&quot;: doc.company}`"
      class="w-full !text-sm !font-mono"
      @update:model-value="(v: string | number) => updateField('link_filters', String(v).trim() || null)"
    />
    <p class="text-muted-foreground">{{ t('JSON object or') }} <code class="bg-muted px-1 rounded">eval: {"field": doc.field}</code></p>
  </div>
</template>
