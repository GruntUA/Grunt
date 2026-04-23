<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { metaApi } from '@/core/api'
import type { DocTypeSummary } from '@/types'

const { field, updateField } = usePropertyEditor()
const childDoctypes = ref<DocTypeSummary[]>([])

onMounted(async () => {
  try {
    const all = await metaApi.list()
    childDoctypes.value = all.filter(d => d.is_child)
  } catch {}
})
</script>

<template>
  <Divider class="!mb-3" />
  <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Child DocType</p>
  <div class="mb-4">
    <Select
      :model-value="field.options ?? ''"
      :options="childDoctypes.map(d => d.name)"
      placeholder="— оберіть —"
      filter
      empty-filter-message="Нічого не знайдено"
      class="w-full"
      @update:model-value="updateField('options', $event)"
    />
  </div>
</template>
