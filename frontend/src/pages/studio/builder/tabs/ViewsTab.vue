<script setup lang="ts">
import { computed } from 'vue'
import { useBuilderStore } from '@/stores/builder'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { X, List, FileText, Columns3, Calendar, Plus } from 'lucide-vue-next'

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

const dateFields = computed(() =>
  dataFields.value.filter(f => ['Date', 'Datetime'].includes(f.fieldtype))
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

function toggleKanban(enabled: boolean) {
  if (enabled) {
    const firstSelect = selectFields.value[0]?.fieldname ?? ''
    builder.updateDocType({ kanban_view: { column_field: firstSelect, title_field: 'name', color_field: null } })
  } else {
    builder.updateDocType({ kanban_view: null })
  }
}

function updateKanban(patch: Record<string, unknown>) {
  if (!builder.doctype?.kanban_view) return
  builder.updateDocType({ kanban_view: { ...builder.doctype.kanban_view, ...patch } })
}

// ── Calendar View ──
const hasCalendar = computed(() => !!builder.doctype?.calendar_view)

function toggleCalendar(enabled: boolean) {
  if (enabled) {
    const firstDate = dateFields.value.length > 0 ? dateFields.value[0].fieldname : ''
    builder.updateDocType({
      calendar_view: {
        field: firstDate,
        title_field: 'name',
        sources: []
      }
    })
  } else {
    builder.updateDocType({ calendar_view: null })
  }
}

function updateCalendar(patch: Record<string, any>) {
  if (!builder.doctype?.calendar_view) return
  builder.updateDocType({ calendar_view: { ...builder.doctype.calendar_view, ...patch } })
}

function addCalendarSource() {
  if (!builder.doctype?.calendar_view) return
  const sources = [...(builder.doctype.calendar_view.sources || [])]
  sources.push({ doctype: '', date_field: '', label_field: 'name' })
  updateCalendar({ sources })
}

function removeCalendarSource(index: number) {
  if (!builder.doctype?.calendar_view) return
  const sources = [...(builder.doctype.calendar_view.sources || [])]
  sources.splice(index, 1)
  updateCalendar({ sources })
}

function updateCalendarSource(index: number, patch: Record<string, any>) {
  if (!builder.doctype?.calendar_view) return
  const sources = [...(builder.doctype.calendar_view.sources || [])]
  sources[index] = { ...sources[index], ...patch }
  updateCalendar({ sources })
}
</script>

<template>
  <div class="max-w-2xl mx-auto p-6 space-y-5 overflow-y-auto h-full pb-24">

    <!-- List View -->
    <div class="rounded-lg border border-border bg-card overflow-hidden">
      <div class="flex items-center gap-2.5 px-4 py-3 bg-muted/40 border-b border-border">
        <List class="size-4 text-muted-foreground" />
        <h3 class="text-sm font-semibold text-foreground">Список</h3>
      </div>
      <div class="p-4 space-y-4">
        <!-- Visible columns -->
        <div class="space-y-2">
          <Label class="text-xs text-muted-foreground">Видимі колонки</Label>
          <div class="flex flex-wrap gap-1.5">
            <Badge v-for="fname in listViewFields" :key="fname" variant="secondary" class="gap-1 text-xs">
              {{ dataFields.find(f => f.fieldname === fname)?.label ?? fname }}
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
              <SelectItem v-for="f in availableListFields" :key="f.fieldname" :value="f.fieldname">
                {{ f.label }}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        <!-- Sort -->
        <div class="grid grid-cols-2 gap-3">
          <div class="space-y-1.5">
            <Label class="text-xs text-muted-foreground">Сортування за</Label>
            <Select :model-value="listView.sort_by" @update:model-value="updateListView({ sort_by: $event })">
              <SelectTrigger class="h-8 text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="name">name</SelectItem>
                <SelectItem value="created_at">created_at</SelectItem>
                <SelectItem value="modified_at">modified_at</SelectItem>
                <SelectItem v-for="f in dataFields" :key="f.fieldname" :value="f.fieldname">{{ f.label }}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div class="space-y-1.5">
            <Label class="text-xs text-muted-foreground">Порядок</Label>
            <Select :model-value="listView.sort_order" @update:model-value="updateListView({ sort_order: $event })">
              <SelectTrigger class="h-8 text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="asc">За зростанням</SelectItem>
                <SelectItem value="desc">За спаданням</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>
    </div>

    <!-- Form View -->
    <div class="rounded-lg border border-border bg-card overflow-hidden">
      <div class="flex items-center gap-2.5 px-4 py-3 bg-muted/40 border-b border-border">
        <FileText class="size-4 text-muted-foreground" />
        <h3 class="text-sm font-semibold text-foreground">Форма</h3>
      </div>
      <div class="p-4">
        <div class="grid grid-cols-2 gap-3">
          <div class="space-y-1.5">
            <Label class="text-xs text-muted-foreground">Розкладка</Label>
            <Select :model-value="formView.layout" @update:model-value="updateFormView({ layout: $event })">
              <SelectTrigger class="h-8 text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="standard">Стандартна</SelectItem>
                <SelectItem value="compact">Компактна</SelectItem>
                <SelectItem value="wide">Широка</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div class="space-y-1.5">
            <Label class="text-xs text-muted-foreground">Формат друку</Label>
            <Input :model-value="formView.print_format ?? ''" placeholder="Назва шаблону" class="h-8 text-xs" @update:model-value="updateFormView({ print_format: $event || null })" />
          </div>
        </div>
      </div>
    </div>

    <!-- Kanban View -->
    <div v-if="builder.doctype" class="rounded-lg border border-border bg-card overflow-hidden">
      <div class="flex items-center justify-between px-4 py-3 bg-muted/40 border-b border-border">
        <div class="flex items-center gap-2.5">
          <Columns3 class="size-4 text-muted-foreground" />
          <h3 class="text-sm font-semibold text-foreground">Канбан</h3>
        </div>
        <Switch :checked="hasKanban" @update:checked="toggleKanban" />
      </div>
      <div v-if="builder.doctype.kanban_view" class="p-4 space-y-3">
        <div class="grid grid-cols-2 gap-3">
          <div class="space-y-1.5">
            <Label class="text-xs text-muted-foreground">Поле колонок *</Label>
            <Select :model-value="builder.doctype.kanban_view.column_field" @update:model-value="updateKanban({ column_field: $event })">
              <SelectTrigger class="h-8 text-xs"><SelectValue placeholder="Оберіть Select поле" /></SelectTrigger>
              <SelectContent>
                <SelectItem v-for="f in selectFields" :key="f.fieldname" :value="f.fieldname">{{ f.label }}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div class="space-y-1.5">
            <Label class="text-xs text-muted-foreground">Поле заголовка</Label>
            <Select :model-value="builder.doctype.kanban_view.title_field" @update:model-value="updateKanban({ title_field: $event })">
              <SelectTrigger class="h-8 text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="name">name</SelectItem>
                <SelectItem v-for="f in dataFields" :key="f.fieldname" :value="f.fieldname">{{ f.label }}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <div class="space-y-1.5">
          <Label class="text-xs text-muted-foreground">Поле кольору (опціонально)</Label>
          <Select :model-value="builder.doctype.kanban_view.color_field ?? '__none__'" @update:model-value="updateKanban({ color_field: $event === '__none__' ? null : $event })">
            <SelectTrigger class="h-8 text-xs"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="__none__">— немає —</SelectItem>
              <SelectItem v-for="f in dataFields.filter(ff => ff.fieldtype === 'Color' || ff.fieldtype === 'Select')" :key="f.fieldname" :value="f.fieldname">{{ f.label }}</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
    </div>

    <!-- Calendar View -->
    <div v-if="builder.doctype" class="rounded-lg border border-border bg-card overflow-hidden">
      <div class="flex items-center justify-between px-4 py-3 bg-muted/40 border-b border-border">
        <div class="flex items-center gap-2.5">
          <Calendar class="size-4 text-muted-foreground" />
          <h3 class="text-sm font-semibold text-foreground">Календар</h3>
        </div>
        <Switch :checked="hasCalendar" @update:checked="toggleCalendar" />
      </div>
      <div v-if="builder.doctype.calendar_view" class="p-4 space-y-4">
        <div class="grid grid-cols-2 gap-3">
          <div class="space-y-1.5">
            <Label class="text-xs text-muted-foreground">Поле дати (Початок) *</Label>
            <Select :model-value="builder.doctype.calendar_view.field" @update:model-value="updateCalendar({ field: $event })">
              <SelectTrigger class="h-8 text-xs"><SelectValue placeholder="Оберіть поле дати" /></SelectTrigger>
              <SelectContent>
                <SelectItem v-for="f in dateFields" :key="f.fieldname" :value="f.fieldname">{{ f.label }}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div class="space-y-1.5">
            <Label class="text-xs text-muted-foreground">Поле дати (Завершення)</Label>
            <Select :model-value="builder.doctype.calendar_view.end_field ?? '__none__'" @update:model-value="updateCalendar({ end_field: $event === '__none__' ? undefined : $event })">
              <SelectTrigger class="h-8 text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">— немає (один день) —</SelectItem>
                <SelectItem v-for="f in dateFields" :key="f.fieldname" :value="f.fieldname">{{ f.label }}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div class="space-y-1.5">
          <Label class="text-xs text-muted-foreground">Поле заголовка</Label>
          <Select :model-value="builder.doctype.calendar_view.title_field" @update:model-value="updateCalendar({ title_field: $event })">
            <SelectTrigger class="h-8 text-xs"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="name">name</SelectItem>
              <SelectItem v-for="f in dataFields" :key="f.fieldname" :value="f.fieldname">{{ f.label }}</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <!-- Sources -->
        <div class="space-y-3 pt-1">
          <div class="flex items-center justify-between">
            <Label class="text-xs font-medium text-muted-foreground">Додаткові джерела</Label>
            <Button variant="outline" size="sm" class="h-7 px-2.5 text-xs gap-1" @click="addCalendarSource">
              <Plus class="size-3" />
              Додати
            </Button>
          </div>

          <div v-for="(source, idx) in builder.doctype.calendar_view.sources || []" :key="idx" class="p-3 border border-border rounded-md space-y-3 bg-muted/20 relative">
            <button class="absolute top-2 right-2 text-muted-foreground hover:text-destructive transition-colors" @click="removeCalendarSource(idx)">
              <X class="size-3.5" />
            </button>

            <div class="grid grid-cols-2 gap-3">
              <div class="space-y-1">
                <Label class="text-[11px] text-muted-foreground">DocType</Label>
                <Input :model-value="source.doctype" placeholder="Наприклад: Task" class="h-7 text-xs" @update:model-value="updateCalendarSource(idx, { doctype: $event })" />
              </div>
              <div class="space-y-1">
                <Label class="text-[11px] text-muted-foreground">Поле дати (start)</Label>
                <Input :model-value="source.date_field" placeholder="fieldname" class="h-7 text-xs" @update:model-value="updateCalendarSource(idx, { date_field: $event })" />
              </div>
              <div class="space-y-1">
                <Label class="text-[11px] text-muted-foreground">Поле дати (end)</Label>
                <Input :model-value="source.end_date_field ?? ''" placeholder="опціонально" class="h-7 text-xs" @update:model-value="updateCalendarSource(idx, { end_date_field: $event || undefined })" />
              </div>
              <div class="space-y-1">
                <Label class="text-[11px] text-muted-foreground">Колір</Label>
                <Input :model-value="source.color ?? ''" placeholder="#hex" class="h-7 text-xs" @update:model-value="updateCalendarSource(idx, { color: $event || undefined })" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

  </div>
</template>
