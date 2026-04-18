<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { metaApi } from '@/core/api'
import type { DocTypeSummary } from '@/types'
import { Separator } from '@/components/ui/separator'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

const { field, updateField } = usePropertyEditor()

const childDoctypes = ref<DocTypeSummary[]>([])
const search = ref('')

onMounted(async () => {
  try {
    const all = await metaApi.list()
    childDoctypes.value = all.filter(d => d.is_child)
  } catch {}
})

const options = computed(() => {
  const q = search.value.toLowerCase()
  return childDoctypes.value.map(d => d.name).filter(n => n && (!q || n.toLowerCase().includes(q)))
})
</script>

<template>
  <Separator class="mb-3" />
  <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Child DocType</p>
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
</template>
