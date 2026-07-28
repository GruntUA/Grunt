<script setup lang="ts">
import { computed } from 'vue'
import { LayoutList, X } from '@lucide/vue'
import { useBuilderFields } from '@/core/composables/useBuilderFields'

const { builder, dataFields } = useBuilderFields()

const listView = computed(
  () => builder.doctype?.list_view ?? { fields: [], sort_by: 'name', sort_order: 'asc' as const, default_filters: {} },
)
const listViewFields = computed(() => listView.value.fields)
const availableListFields = computed(() =>
  dataFields.value.filter((f) => !listViewFields.value.includes(f.fieldname)),
)

function addListField(fieldname: string | number | bigint | Record<string, unknown> | null) {
  const fields = [...listViewFields.value, String(fieldname)]
  builder.updateDocType({ list_view: { ...listView.value, fields } })
}

function removeListField(fieldname: string) {
  const fields = listViewFields.value.filter((f) => f !== fieldname)
  builder.updateDocType({ list_view: { ...listView.value, fields } })
}

function updateListView(patch: Record<string, unknown>) {
  builder.updateDocType({ list_view: { ...listView.value, ...patch } })
}
</script>

<template>
  <div class="rounded-lg border border-border bg-card shadow-sm overflow-hidden">
    <div class="flex items-center gap-2.5 px-4 py-3 bg-muted/40 border-b border-border">
      <LayoutList class="size-4 text-muted-foreground" />
      <h3 class="text-sm font-semibold text-foreground">Відображення: Список</h3>
    </div>
    <div class="p-4 space-y-4">
      <!-- Visible columns -->
      <div class="flex flex-col gap-2">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Видимі колонки</label>
        <div class="flex flex-wrap gap-1.5">
          <Badge v-for="fname in listViewFields" :key="fname" variant="secondary" class="gap-1 text-xs">
            {{ dataFields.find((f) => f.fieldname === fname)?.label ?? fname }}
            <button type="button" class="ml-0.5 hover:text-destructive" @click="removeListField(fname)">
              <X class="size-3" />
            </button>
          </Badge>
          <span v-if="listViewFields.length === 0" class="text-xs text-muted-foreground italic">Не обрано — покаже name</span>
        </div>
        <Select v-if="availableListFields.length > 0" @update:model-value="addListField">
          <SelectTrigger class="w-48 h-8 text-xs">
            <SelectValue placeholder="Додати колонку..." />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="opt in availableListFields.map((f) => ({ value: f.fieldname, label: f.label }))" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <!-- Sort -->
      <div class="grid grid-cols-2 gap-3">
        <div class="flex flex-col gap-1.5">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Сортування за</label>
          <Select :model-value="listView.sort_by" @update:model-value="updateListView({ sort_by: $event })">
            <SelectTrigger class="h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="opt in [
              { value: 'name', label: 'name' },
              { value: 'created_at', label: 'created_at' },
              { value: 'modified_at', label: 'modified_at' },
              ...dataFields.map((f) => ({ value: f.fieldname, label: f.label })),
            ]" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div class="flex flex-col gap-1.5">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Порядок</label>
          <Select :model-value="listView.sort_order" @update:model-value="updateListView({ sort_order: $event })">
            <SelectTrigger class="h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="opt in [
              { value: 'asc', label: 'За зростанням' },
              { value: 'desc', label: 'За спаданням' },
            ]" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
    </div>
  </div>
</template>
