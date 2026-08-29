<script setup lang="ts">
import { computed } from 'vue'
import { ChartGantt } from '@lucide/vue'
import { useBuilderFields } from '@/core/composables/useBuilderFields'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import type { DocTypeGanttView } from '@/types'

const { builder, dataFields, selectFields, allDateFields } = useBuilderFields()

const gantt = computed(() => builder.doctype?.gantt_view ?? null)
const enabled = computed(() => !!gantt.value)

const numberFields = computed(() =>
  dataFields.value.filter((f) => ['Float', 'Int', 'Percent'].includes(f.fieldtype)),
)

const NONE = '__none__'

function toggle(on: boolean) {
  if (on) {
    const dates = allDateFields.value.map((f) => f.fieldname)
    builder.updateDocType({
      gantt_view: {
        start_field: dates[0] ?? '',
        end_field: dates[1] ?? dates[0] ?? '',
        title_field: builder.doctype?.title_field || 'name',
      },
    })
  } else {
    builder.updateDocType({ gantt_view: null })
  }
}

function patch(p: Partial<DocTypeGanttView>) {
  if (!gantt.value) return
  builder.updateDocType({ gantt_view: { ...gantt.value, ...p } })
}

function colorMapText() {
  const m = gantt.value?.color_map
  return m && Object.keys(m).length ? JSON.stringify(m) : ''
}
function setColorMap(raw: unknown) {
  const text = String(raw ?? '').trim()
  if (!text) return patch({ color_map: undefined })
  try {
    const parsed = JSON.parse(text)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) patch({ color_map: parsed })
  } catch {
    /* keep last valid value while typing */
  }
}

const dateOpts = computed(() => allDateFields.value.map((f) => ({ value: f.fieldname, label: f.label })))
const titleOpts = computed(() => [
  { value: 'name', label: 'name' },
  ...dataFields.value.map((f) => ({ value: f.fieldname, label: f.label })),
])
</script>

<template>
  <div v-if="builder.doctype" class="rounded-lg border border-border bg-card shadow-sm overflow-hidden">
    <div class="flex items-center justify-between px-4 py-3 bg-muted/40 border-b border-border">
      <div class="flex items-center gap-2.5">
        <ChartGantt class="size-4 text-muted-foreground" />
        <h3 class="font-semibold text-foreground">Відображення: Діаграма Ганта</h3>
        <span v-if="enabled"
          class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-amber-500/15 text-amber-700 dark:text-amber-400">Увімкнено</span>
      </div>
      <Switch :model-value="enabled" @update:model-value="toggle" />
    </div>

    <div v-if="gantt" class="p-4 space-y-4">
      <div class="grid grid-cols-2 gap-3">
        <div class="flex flex-col gap-1.5">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Поле початку *</label>
          <Select :model-value="gantt.start_field" @update:model-value="patch({ start_field: String($event) })">
            <SelectTrigger class="h-8 text-xs"><SelectValue placeholder="Оберіть поле" /></SelectTrigger>
            <SelectContent>
              <SelectItem v-for="o in dateOpts" :key="o.value" :value="o.value">{{ o.label }}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div class="flex flex-col gap-1.5">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Поле завершення *</label>
          <Select :model-value="gantt.end_field" @update:model-value="patch({ end_field: String($event) })">
            <SelectTrigger class="h-8 text-xs"><SelectValue placeholder="Оберіть поле" /></SelectTrigger>
            <SelectContent>
              <SelectItem v-for="o in dateOpts" :key="o.value" :value="o.value">{{ o.label }}</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div class="grid grid-cols-2 gap-3">
        <div class="flex flex-col gap-1.5">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Поле заголовка</label>
          <Select :model-value="gantt.title_field || 'name'" @update:model-value="patch({ title_field: String($event) })">
            <SelectTrigger class="h-8 text-xs"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem v-for="o in titleOpts" :key="o.value" :value="o.value">{{ o.label }}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div class="flex flex-col gap-1.5">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Поле прогресу (0–100)</label>
          <Select :model-value="gantt.progress_field || NONE"
            @update:model-value="patch({ progress_field: $event === NONE ? undefined : String($event) })">
            <SelectTrigger class="h-8 text-xs"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem :value="NONE">— немає —</SelectItem>
              <SelectItem v-for="f in numberFields" :key="f.fieldname" :value="f.fieldname">{{ f.label }}</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div class="grid grid-cols-2 gap-3">
        <div class="flex flex-col gap-1.5">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Колір за полем</label>
          <Select :model-value="gantt.color_field || NONE"
            @update:model-value="patch({ color_field: $event === NONE ? undefined : String($event) })">
            <SelectTrigger class="h-8 text-xs"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem :value="NONE">— немає —</SelectItem>
              <SelectItem v-for="f in selectFields" :key="f.fieldname" :value="f.fieldname">{{ f.label }}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div class="flex flex-col gap-1.5">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Колір за замовчуванням</label>
          <Input :model-value="gantt.default_color ?? ''" placeholder="#2563eb або var(--primary)"
            class="h-8 text-xs" @update:model-value="patch({ default_color: String($event || '') || undefined })" />
        </div>
      </div>

      <div v-if="gantt.color_field" class="flex flex-col gap-1.5">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Мапа кольорів (JSON)</label>
        <Input :model-value="colorMapText()" placeholder='{"В роботі":"#f59e0b","Готово":"#16a34a"}'
          class="h-8 text-xs" @update:model-value="setColorMap($event)" />
      </div>

      <div class="flex flex-col gap-1.5">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Поле залежностей</label>
        <Select :model-value="gantt.dependencies_field || NONE"
          @update:model-value="patch({ dependencies_field: $event === NONE ? undefined : String($event) })">
          <SelectTrigger class="h-8 text-xs"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem :value="NONE">— немає —</SelectItem>
            <SelectItem v-for="f in dataFields" :key="f.fieldname" :value="f.fieldname">{{ f.label }}</SelectItem>
          </SelectContent>
        </Select>
        <p class="text-[11px] text-muted-foreground">
          Текстове поле зі списком name документів-попередників через кому — між ними малюються стрілки.
        </p>
      </div>
    </div>
  </div>
</template>
