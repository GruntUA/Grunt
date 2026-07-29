<script setup lang="ts">
import { computed } from 'vue'
import { LayoutGrid } from '@lucide/vue'
import { useBuilderFields } from '@/core/composables/useBuilderFields'

const { builder, dataFields, selectFields } = useBuilderFields()

const hasKanban = computed(() => !!builder.doctype?.kanban_view)

function toggleKanban(enabled: boolean) {
  if (enabled) {
    const firstSelect = selectFields.value[0]?.fieldname ?? ''
    builder.updateDocType({
      kanban_view: { column_field: firstSelect, title_field: 'name', color_field: null },
    })
  } else {
    builder.updateDocType({ kanban_view: null })
  }
}

function updateKanban(patch: Record<string, unknown>) {
  if (!builder.doctype?.kanban_view) return
  builder.updateDocType({ kanban_view: { ...builder.doctype.kanban_view, ...patch } })
}

const colorOrSelectFields = computed(() =>
  dataFields.value.filter(
    (ff) => ff.fieldtype === 'Color' || ff.fieldtype === 'Select',
  ),
)
</script>

<template>
  <div v-if="builder.doctype" class="rounded-lg border border-border bg-card shadow-sm overflow-hidden">
    <div class="flex items-center justify-between px-4 py-3 bg-muted/40 border-b border-border">
      <div class="flex items-center gap-2.5">
        <LayoutGrid class="size-4 text-muted-foreground" />
        <h3 class="text-sm font-semibold text-foreground">Відображення: Канбан</h3>
        <span
          v-if="hasKanban"
          class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-500/15 text-blue-700 dark:text-blue-400"
        >Увімкнено</span>
      </div>
      <Switch :model-value="hasKanban" @update:model-value="toggleKanban" />
    </div>
    <div v-if="builder.doctype.kanban_view" class="p-4 space-y-3">
      <div class="grid grid-cols-2 gap-3">
        <div class="flex flex-col gap-1.5">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Поле колонок *</label>
          <Select :model-value="builder.doctype.kanban_view.column_field" @update:model-value="updateKanban({ column_field: $event })">
            <SelectTrigger class="h-8 text-xs">
              <SelectValue placeholder="Оберіть Select поле" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="opt in selectFields.map((f) => ({ value: f.fieldname, label: f.label }))" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div class="flex flex-col gap-1.5">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Поле заголовка</label>
          <Select :model-value="builder.doctype.kanban_view.title_field" @update:model-value="updateKanban({ title_field: $event })">
            <SelectTrigger class="h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="opt in [{ value: 'name', label: 'name' }, ...dataFields.map((f) => ({ value: f.fieldname, label: f.label }))]" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Поле кольору (опціонально)</label>
        <Select :model-value="builder.doctype.kanban_view.color_field ?? '__none__'" @update:model-value="updateKanban({ color_field: $event === '__none__' ? null : $event })">
          <SelectTrigger class="h-8 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="opt in [{ value: '__none__', label: '— немає —' }, ...colorOrSelectFields.map((f) => ({ value: f.fieldname, label: f.label }))]" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
          </SelectContent>
        </Select>
      </div>
    </div>
  </div>
</template>
