<script setup lang="ts">
import { computed } from 'vue'
import { useBuilderStore } from '@/stores/builder'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Separator } from '@/components/ui/separator'
import { Badge } from '@/components/ui/badge'
import { X } from 'lucide-vue-next'

const builder = useBuilderStore()

// Data fields — non-layout fields for selects
const dataFields = computed(() =>
  (builder.doctype?.fields ?? []).filter(f =>
    !['Section', 'Column', 'Tab'].includes(f.fieldtype)
  )
)

const selectFields = computed(() =>
  dataFields.value.filter(f => f.fieldtype === 'Select')
)

// ── List View ──
const listView = computed(() => builder.doctype?.list_view ?? { fields: [], sort_by: 'name', sort_order: 'asc' as const, default_filters: {} })

const listViewFields = computed(() => listView.value.fields)
const availableListFields = computed(() =>
  dataFields.value.filter(f => !listViewFields.value.includes(f.fieldname))
)

function addListField(fieldname: string | number | bigint | Record<string, any> | null) {
  const fields = [...listViewFields.value, String(fieldname)]
  builder.updateDocType({ list_view: { ...listView.value, fields } })
}

function removeListField(fieldname: string) {
  const fields = listViewFields.value.filter(f => f !== fieldname)
  builder.updateDocType({ list_view: { ...listView.value, fields } })
}

function updateListView(patch: Record<string, unknown>) {
  builder.updateDocType({ list_view: { ...listView.value, ...patch } })
}

// ── Form View ──
const formView = computed(() => builder.doctype?.form_view ?? { layout: 'standard' as const, print_format: null })

function updateFormView(patch: Record<string, unknown>) {
  builder.updateDocType({ form_view: { ...formView.value, ...patch } })
}

// ── Kanban View ──
const hasKanban = computed(() => !!builder.doctype?.kanban_view)
const kanbanView = computed(() => builder.doctype?.kanban_view ?? { column_field: '', title_field: 'name', color_field: null })

function toggleKanban(enabled: boolean) {
  if (enabled) {
    const firstSelect = selectFields.value[0]?.fieldname ?? ''
    builder.updateDocType({ kanban_view: { column_field: firstSelect, title_field: 'name', color_field: null } })
  } else {
    builder.updateDocType({ kanban_view: null })
  }
}

function updateKanban(patch: Record<string, unknown>) {
  builder.updateDocType({ kanban_view: { ...kanbanView.value, ...patch } })
}
</script>

<template>
  <div class="max-w-2xl mx-auto p-6 space-y-8 overflow-y-auto h-full">
    <!-- List View -->
    <section class="space-y-4">
      <h3 class="text-sm font-semibold text-foreground">Список (ListView)</h3>

      <!-- Visible columns -->
      <div class="space-y-2">
        <Label class="text-sm">Видимі колонки</Label>
        <div class="flex flex-wrap gap-1.5">
          <Badge v-for="fname in listViewFields" :key="fname" variant="secondary" class="gap-1">
            {{ dataFields.find(f => f.fieldname === fname)?.label ?? fname }}
            <button type="button" class="ml-0.5 hover:text-destructive" @click="removeListField(fname)">
              <X class="size-3" />
            </button>
          </Badge>
          <span v-if="listViewFields.length === 0" class="text-sm text-muted-foreground">Не обрано — покаже name</span>
        </div>
        <Select v-if="availableListFields.length > 0" @update:model-value="addListField">
          <SelectTrigger class="w-48">
            <SelectValue placeholder="Додати колонку..." />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="f in availableListFields" :key="f.fieldname" :value="f.fieldname">
              {{ f.label }}
            </SelectItem>
          </SelectContent>
        </Select>
      </div>

      <!-- Sort -->
      <div class="grid grid-cols-2 gap-3">
        <div class="space-y-1.5">
          <Label class="text-sm">Сортування за</Label>
          <Select :model-value="listView.sort_by" @update:model-value="updateListView({ sort_by: $event })">
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="name">name</SelectItem>
              <SelectItem value="created_at">created_at</SelectItem>
              <SelectItem value="modified_at">modified_at</SelectItem>
              <SelectItem v-for="f in dataFields" :key="f.fieldname" :value="f.fieldname">{{ f.label }}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div class="space-y-1.5">
          <Label class="text-sm">Порядок</Label>
          <Select :model-value="listView.sort_order" @update:model-value="updateListView({ sort_order: $event })">
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="asc">За зростанням</SelectItem>
              <SelectItem value="desc">За спаданням</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
    </section>

    <Separator />

    <!-- Form View -->
    <section class="space-y-4">
      <h3 class="text-sm font-semibold text-foreground">Форма (FormView)</h3>

      <div class="grid grid-cols-2 gap-3">
        <div class="space-y-1.5">
          <Label class="text-sm">Розкладка</Label>
          <Select :model-value="formView.layout" @update:model-value="updateFormView({ layout: $event })">
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="standard">Стандартна</SelectItem>
              <SelectItem value="compact">Компактна</SelectItem>
              <SelectItem value="wide">Широка</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div class="space-y-1.5">
          <Label class="text-sm">Формат друку</Label>
          <Input :model-value="formView.print_format ?? ''" placeholder="Назва шаблону" @update:model-value="updateFormView({ print_format: $event || null })" />
        </div>
      </div>
    </section>

    <Separator />

    <!-- Kanban View -->
    <section class="space-y-4">
      <div class="flex items-center gap-3">
        <h3 class="text-sm font-semibold text-foreground">Канбан (KanbanView)</h3>
        <Switch :checked="hasKanban" @update:checked="toggleKanban" />
      </div>

      <template v-if="hasKanban">
        <div class="grid grid-cols-2 gap-3">
          <div class="space-y-1.5">
            <Label class="text-sm">Поле колонок *</Label>
            <Select :model-value="kanbanView.column_field" @update:model-value="updateKanban({ column_field: $event })">
              <SelectTrigger><SelectValue placeholder="Оберіть Select поле" /></SelectTrigger>
              <SelectContent>
                <SelectItem v-for="f in selectFields" :key="f.fieldname" :value="f.fieldname">{{ f.label }}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div class="space-y-1.5">
            <Label class="text-sm">Поле заголовка</Label>
            <Select :model-value="kanbanView.title_field" @update:model-value="updateKanban({ title_field: $event })">
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="name">name</SelectItem>
                <SelectItem v-for="f in dataFields" :key="f.fieldname" :value="f.fieldname">{{ f.label }}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <div class="space-y-1.5">
          <Label class="text-sm">Поле кольору (опціонально)</Label>
          <Select :model-value="kanbanView.color_field ?? '__none__'" @update:model-value="updateKanban({ color_field: $event === '__none__' ? null : $event })">
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="__none__">— немає —</SelectItem>
              <SelectItem v-for="f in dataFields.filter(ff => ff.fieldtype === 'Color' || ff.fieldtype === 'Select')" :key="f.fieldname" :value="f.fieldname">{{ f.label }}</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </template>
    </section>
  </div>
</template>
