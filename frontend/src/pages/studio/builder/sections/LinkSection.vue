<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { metaApi } from '@/core/api'
import type { DocTypeSummary } from '@/types'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

const { field, updateField } = usePropertyEditor()

const doctypeList = ref<DocTypeSummary[]>([])
const search = ref('')

onMounted(async () => {
  try { doctypeList.value = await metaApi.list() } catch {}
})

const options = computed(() => {
  const q = search.value.toLowerCase()
  return doctypeList.value.map(d => d.name).filter(n => n && (!q || n.toLowerCase().includes(q)))
})
</script>

<template>
  <Separator class="mb-3" />
  <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Linked DocType</p>
  <div class="mb-4">
    <Select
      :model-value="field.options ?? ''"
      @update:model-value="updateField('options', $event)"
      @update:open="(o) => { if (!o) search = '' }"
    >
      <SelectTrigger><SelectValue placeholder="— оберіть —" /></SelectTrigger>
      <SelectContent>
        <div class="px-2 pb-1">
          <input
            v-model="search"
            placeholder="Пошук..."
            class="w-full h-7 px-2 text-sm rounded border border-input bg-background outline-none focus:ring-1 focus:ring-ring"
            @keydown.stop
          />
        </div>
        <SelectItem v-for="opt in options" :key="opt" :value="opt">{{ opt }}</SelectItem>
        <div v-if="!options.length" class="px-2 py-1.5 text-xs text-muted-foreground">Нічого не знайдено</div>
      </SelectContent>
    </Select>
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
