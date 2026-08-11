<script setup lang="ts">
import { computed } from 'vue'
import { CalendarDays, Plus, X } from '@lucide/vue'
import { useBuilderFields } from '@/core/composables/useBuilderFields'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'

const { builder, dataFields, allDateFields } = useBuilderFields()

const hasCalendar = computed(() => !!builder.doctype?.calendar_view)

function toggleCalendar(enabled: boolean) {
  if (enabled) {
    const firstDate = allDateFields.value.length > 0 ? allDateFields.value[0].fieldname : ''
    builder.updateDocType({
      calendar_view: {
        field: firstDate,
        title_field: 'name',
        sources: [],
      },
    })
  } else {
    builder.updateDocType({ calendar_view: null })
  }
}

function updateCalendar(patch: Record<string, unknown>) {
  if (!builder.doctype?.calendar_view) return
  builder.updateDocType({ calendar_view: { ...builder.doctype.calendar_view, ...patch } })
}

function addCalendarSource() {
  if (!builder.doctype?.calendar_view) return
  const sources = [...(builder.doctype.calendar_view.sources || [])]
  sources.push({
    doctype: '',
    date_field: '',
    label_field: 'name',
    filters: {},
    recurring: false,
    event_type: 'default',
    show_age: false,
    remind_before_days: 1,
  })
  updateCalendar({ sources })
}

function removeCalendarSource(index: number) {
  if (!builder.doctype?.calendar_view) return
  const sources = [...(builder.doctype.calendar_view.sources || [])]
  sources.splice(index, 1)
  updateCalendar({ sources })
}

function updateCalendarSource(index: number, patch: Record<string, unknown>) {
  if (!builder.doctype?.calendar_view) return
  const sources = [...(builder.doctype.calendar_view.sources || [])]
  sources[index] = { ...sources[index], ...patch }
  updateCalendar({ sources })
}

function sourceFiltersText(source: Record<string, unknown>) {
  const filters = source.filters || {}
  try {
    return Object.keys(filters).length > 0 ? JSON.stringify(filters) : ''
  } catch {
    return ''
  }
}

function updateCalendarSourceFilters(index: number, raw: string | number | bigint | Record<string, unknown> | null | undefined) {
  const text = String(raw || '').trim()
  if (!text) {
    updateCalendarSource(index, { filters: {} })
    return
  }
  try {
    const parsed = JSON.parse(text)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      updateCalendarSource(index, { filters: parsed })
    }
  } catch {
    // Ignore invalid JSON while editing; persist previous valid value.
  }
}

function updateCalendarSourceReminderDays(index: number, raw: string | number | bigint | Record<string, unknown> | null | undefined) {
  const text = String(raw ?? '').trim()
  if (!text) {
    updateCalendarSource(index, { remind_before_days: undefined })
    return
  }
  const parsed = Number(text)
  if (!Number.isFinite(parsed)) return
  updateCalendarSource(index, { remind_before_days: Math.max(0, Math.floor(parsed)) })
}
</script>

<template>
  <div v-if="builder.doctype" class="rounded-lg border border-border bg-card shadow-sm overflow-hidden">
    <div class="flex items-center justify-between px-4 py-3 bg-muted/40 border-b border-border">
      <div class="flex items-center gap-2.5">
        <CalendarDays class="size-4 text-muted-foreground" />
        <h3 class="text-sm font-semibold text-foreground">Відображення: Календар</h3>
        <span
          v-if="hasCalendar"
          class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-amber-500/15 text-amber-700 dark:text-amber-400"
        >Увімкнено</span>
      </div>
      <Switch :model-value="hasCalendar" @update:model-value="toggleCalendar" />
    </div>
    <div v-if="builder.doctype.calendar_view" class="p-4 space-y-4">
      <div class="grid grid-cols-2 gap-3">
        <div class="flex flex-col gap-1.5">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Поле дати (Початок) *</label>
          <Select :model-value="builder.doctype.calendar_view.field" @update:model-value="updateCalendar({ field: $event })">
            <SelectTrigger class="h-8 text-xs">
              <SelectValue placeholder="Оберіть поле дати" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="opt in allDateFields.map((f) => ({ value: f.fieldname, label: f.label }))" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div class="flex flex-col gap-1.5">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Поле дати (Завершення)</label>
          <Select :model-value="builder.doctype.calendar_view.end_field ?? '__none__'" @update:model-value="updateCalendar({ end_field: $event === '__none__' ? undefined : $event })">
            <SelectTrigger class="h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="opt in [{ value: '__none__', label: '— немає (один день) —' }, ...allDateFields.map((f) => ({ value: f.fieldname, label: f.label }))]" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div class="flex flex-col gap-1.5">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Поле заголовка</label>
        <Select :model-value="builder.doctype.calendar_view.title_field" @update:model-value="updateCalendar({ title_field: $event })">
          <SelectTrigger class="h-8 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="opt in [{ value: 'name', label: 'name' }, ...dataFields.map((f) => ({ value: f.fieldname, label: f.label }))]" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div class="space-y-3 pt-1">
        <div class="flex items-center justify-between">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Додаткові джерела</label>
          <Button variant="outline" size="sm" class="h-7 px-2.5 text-xs gap-1" @click="addCalendarSource">
            <Plus class="size-3" />
            Додати
          </Button>
        </div>

        <div
          v-for="(source, idx) in builder.doctype.calendar_view.sources || []"
          :key="idx"
          class="p-3 border border-border rounded-md space-y-3 bg-muted/20 relative"
        >
          <button
            class="absolute top-2 right-2 text-muted-foreground hover:text-destructive transition-colors"
            @click="removeCalendarSource(idx)"
          >
            <X class="size-3.5" />
          </button>

          <div class="grid grid-cols-2 gap-3">
            <div class="flex flex-col gap-1">
              <label class="text-xs font-medium text-muted-foreground">DocType</label>
              <Input
                :model-value="source.doctype"
                placeholder="Наприклад: Task"
                class="h-7 text-xs w-full"
                @update:model-value="updateCalendarSource(idx, { doctype: $event })"
              />
            </div>
            <div class="flex flex-col gap-1">
              <label class="text-xs font-medium text-muted-foreground">Тип події</label>
              <Select :model-value="source.event_type ?? 'default'" @update:model-value="updateCalendarSource(idx, {
                  event_type: $event,
                  recurring: $event === 'birthday' ? true : (source.recurring ?? false),
                  show_age: $event === 'birthday' ? true : (source.show_age ?? false),
                })">
                <SelectTrigger class="h-7 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem v-for="opt in [
                  { value: 'default', label: 'Звичайна подія' },
                  { value: 'birthday', label: 'День народження' },
                ]" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div class="flex flex-col gap-1">
              <label class="text-xs font-medium text-muted-foreground">Поле дати (start)</label>
              <Input
                :model-value="source.date_field"
                placeholder="fieldname"
                class="h-7 text-xs w-full"
                @update:model-value="updateCalendarSource(idx, { date_field: $event })"
              />
            </div>
            <div class="flex flex-col gap-1">
              <label class="text-xs font-medium text-muted-foreground">Поле дати (end)</label>
              <Input
                :model-value="source.end_date_field ?? ''"
                placeholder="опціонально"
                class="h-7 text-xs w-full"
                @update:model-value="updateCalendarSource(idx, { end_date_field: $event || undefined })"
              />
            </div>
            <div class="flex flex-col gap-1">
              <label class="text-xs font-medium text-muted-foreground">Поле заголовка</label>
              <Input
                :model-value="source.label_field ?? 'name'"
                placeholder="Наприклад: full_name"
                class="h-7 text-xs w-full"
                @update:model-value="updateCalendarSource(idx, { label_field: $event || 'name' })"
              />
            </div>
            <div class="flex flex-col gap-1">
              <label class="text-xs font-medium text-muted-foreground">Колір</label>
              <Input
                :model-value="source.color ?? ''"
                placeholder="#hex"
                class="h-7 text-xs w-full"
                @update:model-value="updateCalendarSource(idx, { color: $event || undefined })"
              />
            </div>
            <div class="flex flex-col gap-1">
              <label class="text-xs font-medium text-muted-foreground">Щорічне повторення</label>
              <Select :model-value="source.recurring ? 'yes' : 'no'" @update:model-value="updateCalendarSource(idx, { recurring: $event === 'yes' })">
                <SelectTrigger class="h-7 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem v-for="opt in [{ value: 'yes', label: 'Так' }, { value: 'no', label: 'Ні' }]" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div v-if="source.event_type === 'birthday'" class="flex flex-col gap-1">
              <label class="text-xs font-medium text-muted-foreground">Показувати вік</label>
              <Select :model-value="source.show_age ? 'yes' : 'no'" @update:model-value="updateCalendarSource(idx, { show_age: $event === 'yes' })">
                <SelectTrigger class="h-7 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem v-for="opt in [{ value: 'yes', label: 'Так' }, { value: 'no', label: 'Ні' }]" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div v-if="source.event_type === 'birthday'" class="flex flex-col gap-1">
              <label class="text-xs font-medium text-muted-foreground">Нагадати за (днів)</label>
              <Input
                :model-value="String(source.remind_before_days ?? 1)"
                placeholder="1"
                class="h-7 text-xs w-full"
                @update:model-value="updateCalendarSourceReminderDays(idx, $event)"
              />
            </div>
            <div class="flex flex-col gap-1 col-span-2">
              <label class="text-xs font-medium text-muted-foreground">Фільтри (JSON)</label>
              <Input
                :model-value="sourceFiltersText(source)"
                placeholder='Наприклад: {"status":"Активний"}'
                class="h-7 text-xs w-full"
                @update:model-value="updateCalendarSourceFilters(idx, $event)"
              />
            </div>
          </div>
          <p v-if="source.event_type === 'birthday'" class="text-xs text-muted-foreground">
            Для співробітників: date_field = birth_date, label_field = full_name, recurring = Так, remind_before_days = 1.
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
