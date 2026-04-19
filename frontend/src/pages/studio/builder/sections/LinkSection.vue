<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { metaApi } from '@/core/api'
import type { DocTypeSummary } from '@/types'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'

const { field, updateField } = usePropertyEditor()
const doctypeList = ref<DocTypeSummary[]>([])

onMounted(async () => {
  try { doctypeList.value = await metaApi.list() } catch {}
})
</script>

<template>
  <Separator class="mb-3" />
  <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Linked DocType</p>
  <div class="mb-4">
    <Select
      :model-value="field.options ?? ''"
      :options="doctypeList.map(d => d.name)"
      placeholder="— оберіть —"
      filter
      empty-filter-message="Нічого не знайдено"
      class="w-full"
      @update:model-value="updateField('options', $event)"
    />
  </div>

  <div v-if="field.options" class="mb-4">
    <Label class="text-sm">Link Filters</Label>
    <textarea
      :value="field.link_filters ?? ''"
      rows="2"
      placeholder='{"status": "Active"} або eval: {"company": doc.company}'
      class="w-full mt-1.5 text-sm font-mono border border-input rounded-md px-2 py-1.5 bg-background focus:outline-none focus:ring-1 focus:ring-ring resize-none"
      @input="updateField('link_filters', ($event.target as HTMLTextAreaElement).value.trim() || null)"
    />
    <p class="text-[11px] text-muted-foreground mt-1">JSON об'єкт або <code class="bg-muted px-1 rounded">eval: {"field": doc.field}</code></p>
  </div>
</template>
