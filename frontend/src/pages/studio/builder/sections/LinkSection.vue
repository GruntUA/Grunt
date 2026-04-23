<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { metaApi } from '@/core/api'
import type { DocTypeSummary } from '@/types'

const { field, updateField } = usePropertyEditor()
const doctypeList = ref<DocTypeSummary[]>([])

onMounted(async () => {
  try { doctypeList.value = await metaApi.list() } catch {}
})
</script>

<template>
  <Divider class="!mb-3" />
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

  <div v-if="field.options" class="mb-4 flex flex-col gap-1.5">
    <label class="text-sm font-medium">Link Filters</label>
    <Textarea
      :model-value="field.link_filters ?? ''"
      rows="2"
      placeholder='{"status": "Active"} або eval: {"company": doc.company}'
      class="w-full !text-sm !font-mono"
      autoResize
      @input="updateField('link_filters', ($event.target as HTMLTextAreaElement).value.trim() || null)"
    />
    <p class="text-[11px] text-muted-foreground">JSON об'єкт або <code class="bg-muted px-1 rounded">eval: {"field": doc.field}</code></p>
  </div>
</template>
