<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useBuilderStore } from '@/stores/builder'
import { getFieldDef } from '@/core/fieldRegistry'
import { metaApi } from '@/core/api'
import type { DocTypeSummary } from '@/types'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { Separator } from '@/components/ui/separator'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { TriangleAlert } from 'lucide-vue-next'

const linkSearch = ref('')
const tableSearch = ref('')

const builder = useBuilderStore()
const field = computed(() => builder.selectedField)
const config = computed(() => field.value ? getFieldDef(field.value.fieldtype) : undefined)
const sections = computed(() => config.value?.propertySections ?? [])

// Table fields in the current DocType (for aggregate_table selector)
const tableFields = computed(() =>
  (builder.doctype?.fields ?? []).filter((f) => f.fieldtype === 'Table')
)
const fieldHint = computed(() =>
  field.value
    ? builder.indexHints.find(h => h.field === field.value!.fieldname) ?? null
    : null
)

function has(section: string) {
  return sections.value.includes(section as never)
}

function updateField(key: string, val: unknown) {
  if (builder.selectedFieldName === null) return
  builder.updateField(builder.selectedFieldName, { [key]: val } as never)
}

// DocType lists for Link / Table selectors
const doctypeList = ref<DocTypeSummary[]>([])
const childDoctypes = ref<DocTypeSummary[]>([])

onMounted(async () => {
  try {
    doctypeList.value = await metaApi.list()
    childDoctypes.value = doctypeList.value.filter((d) => d.is_child)
  } catch {}
})

const doctypeOptions = computed(() => {
  const q = linkSearch.value.toLowerCase()
  return doctypeList.value.map((d) => d.name).filter((n) => n && (!q || n.toLowerCase().includes(q)))
})
const childDoctypeOptions = computed(() => {
  const q = tableSearch.value.toLowerCase()
  return childDoctypes.value.map((d) => d.name).filter((n) => n && (!q || n.toLowerCase().includes(q)))
})
</script>

<template>
  <div class="h-full overflow-y-auto p-4 border-l border-border bg-card">
    <template v-if="field && config">
      <!-- Header -->
      <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-4">
        {{ config.label }}
      </p>

      <!-- Index hint -->
      <div v-if="fieldHint" class="flex gap-2 rounded-md border border-yellow-400 bg-yellow-50 dark:bg-yellow-950/30 p-3 mb-4 text-xs text-yellow-800 dark:text-yellow-300">
        <TriangleAlert class="size-4 shrink-0 mt-px text-yellow-500" />
        <div class="flex-1">
          <p>{{ fieldHint.reason }}</p>
          <button
            type="button"
            class="mt-1.5 font-semibold underline underline-offset-2 hover:opacity-75"
            @click="updateField('index', true)"
          >Додати index: true</button>
        </div>
      </div>

      <!-- CORE: Label + Fieldname -->
      <div v-if="has('core')" class="flex flex-col gap-3 mb-4">
        <div class="space-y-1.5">
          <Label class="text-sm">Label</Label>
          <Input :model-value="field.label" @update:model-value="updateField('label', $event)" />
        </div>
        <div class="space-y-1.5">
          <Label class="text-sm text-muted-foreground">Fieldname</Label>
          <Input
            :model-value="field.fieldname"
            :disabled="['Section','Column','Tab'].includes(field.fieldtype)"
            @update:model-value="updateField('fieldname', $event)"
          />
        </div>
      </div>

      <!-- COLLAPSIBLE: for Section -->
      <div v-if="has('collapsible')" class="mb-4">
        <div class="flex items-center gap-2">
          <Checkbox :model-value="!!field.collapsible" @update:model-value="updateField('collapsible', $event)" />
          <Label class="text-sm">Collapsible</Label>
        </div>
      </div>

      <!-- FLAGS: Required, Hidden, Read Only, Bold, Unique -->
      <template v-if="has('flags')">
        <Separator class="mb-3" />
        <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Flags</p>
        <div class="flex flex-col gap-2 mb-4">
          <div class="flex items-center gap-2">
            <Checkbox :model-value="!!field.required" @update:model-value="updateField('required', $event)" />
            <Label class="text-sm">Required</Label>
          </div>
          <div class="flex items-center gap-2">
            <Checkbox :model-value="!!field.hidden" @update:model-value="updateField('hidden', $event)" />
            <Label class="text-sm">Hidden</Label>
          </div>
          <div class="flex items-center gap-2">
            <Checkbox :model-value="!!field.read_only" @update:model-value="updateField('read_only', $event)" />
            <Label class="text-sm">Read Only</Label>
          </div>
          <div class="flex items-center gap-2">
            <Checkbox :model-value="!!field.bold" @update:model-value="updateField('bold', $event)" />
            <Label class="text-sm">Bold</Label>
          </div>
          <div class="flex items-center gap-2">
            <Checkbox :model-value="!!field.unique" @update:model-value="updateField('unique', $event)" />
            <Label class="text-sm">Unique</Label>
          </div>
          <div class="flex items-center gap-2">
            <Checkbox :model-value="!!field.index" :disabled="!!field.unique" @update:model-value="updateField('index', $event)" />
            <Label class="text-sm" :class="{ 'text-muted-foreground': !!field.unique }">Index</Label>
          </div>
        </div>
      </template>

      <!-- DISPLAY: In List View, In Filter -->
      <template v-if="has('display')">
        <Separator class="mb-3" />
        <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Display</p>
        <div class="flex flex-col gap-2 mb-4">
          <div class="flex items-center gap-2">
            <Checkbox :model-value="!!field.in_list_view" @update:model-value="updateField('in_list_view', $event)" />
            <Label class="text-sm">In List View</Label>
          </div>
          <div class="flex items-center gap-2">
            <Checkbox :model-value="!!field.in_filter" @update:model-value="updateField('in_filter', $event)" />
            <Label class="text-sm">In Filter</Label>
          </div>
          <div class="flex items-center gap-2">
            <Checkbox :model-value="!!field.in_quick_entry" @update:model-value="updateField('in_quick_entry', $event)" />
            <Label class="text-sm">In Quick Entry</Label>
          </div>
        </div>
      </template>

      <!-- TEXT: Description, Placeholder, Depends On, Mandatory Depends On -->
      <template v-if="has('text')">
        <Separator class="mb-3" />
        <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Text</p>
        <div class="flex flex-col gap-3 mb-4">
          <div class="space-y-1.5">
            <Label class="text-sm">Description</Label>
            <Input :model-value="field.description ?? ''" @update:model-value="updateField('description', $event || undefined)" />
          </div>
          <div class="space-y-1.5">
            <Label class="text-sm">Placeholder</Label>
            <Input :model-value="field.placeholder ?? ''" @update:model-value="updateField('placeholder', $event || undefined)" />
          </div>
          <div class="space-y-1.5">
            <Label class="text-sm">Depends On</Label>
            <Input :model-value="field.depends_on ?? ''" placeholder="eval: doc.status == 'Active'" @update:model-value="updateField('depends_on', $event || undefined)" />
          </div>
          <div class="space-y-1.5">
            <Label class="text-sm">Mandatory Depends On</Label>
            <Input :model-value="field.mandatory_depends_on ?? ''" placeholder="eval: doc.type == 'Full'" @update:model-value="updateField('mandatory_depends_on', $event || undefined)" />
          </div>
        </div>
      </template>

      <!-- DEFAULT VALUE -->
      <template v-if="has('default')">
        <Separator class="mb-3" />
        <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Default</p>
        <div class="mb-4">
          <Input
            :model-value="String(field.default ?? '')"
            placeholder="Default value"
            @update:model-value="updateField('default', $event || undefined)"
          />
        </div>
      </template>

      <!-- NUMBER: Min / Max Value -->
      <template v-if="has('number')">
        <Separator class="mb-3" />
        <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Range</p>
        <div class="flex gap-2 mb-4">
          <div class="flex-1 space-y-1.5">
            <Label class="text-sm">Min</Label>
            <Input
              :model-value="String(field.min_value ?? '')"
              type="number"
              @update:model-value="updateField('min_value', $event ? Number($event) : undefined)"
            />
          </div>
          <div class="flex-1 space-y-1.5">
            <Label class="text-sm">Max</Label>
            <Input
              :model-value="String(field.max_value ?? '')"
              type="number"
              @update:model-value="updateField('max_value', $event ? Number($event) : undefined)"
            />
          </div>
        </div>
      </template>

      <!-- VALIDATION: Max Length, Regex -->
      <template v-if="has('validation')">
        <Separator class="mb-3" />
        <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Validation</p>
        <div class="flex flex-col gap-3 mb-4">
          <div v-if="['Text', 'LongText'].includes(field.fieldtype)" class="space-y-1.5">
            <Label class="text-sm">Max Length</Label>
            <Input
              :model-value="String(field.max_length ?? '')"
              type="number"
              placeholder="255"
              @update:model-value="updateField('max_length', $event ? Number($event) : undefined)"
            />
          </div>
          <div class="space-y-1.5">
            <Label class="text-sm">Regex</Label>
            <Input
              :model-value="field.regex ?? ''"
              placeholder="^[A-Z].*"
              @update:model-value="updateField('regex', $event || undefined)"
            />
          </div>
        </div>
      </template>

      <!-- FORMULA -->
      <template v-if="has('formula')">
        <Separator class="mb-3" />
        <div class="flex items-center justify-between mb-3">
          <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Formula</p>
          <span
            v-if="field.formula"
            class="text-[10px] font-mono text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 px-1.5 py-0.5 rounded"
          >ƒx активна</span>
        </div>
        <div class="flex flex-col gap-2 mb-4">
          <div class="space-y-1.5">
            <Label class="text-sm">Вираз (Python)</Label>
            <textarea
              :value="field.formula ?? ''"
              rows="2"
              placeholder="qty * unit_price"
              class="w-full text-sm font-mono border border-input rounded-md px-2 py-1.5 bg-background focus:outline-none focus:ring-1 focus:ring-ring resize-none"
              @input="updateField('formula', ($event.target as HTMLTextAreaElement).value.trim() || null)"
            />
            <p class="text-[11px] text-muted-foreground leading-relaxed">
              Обчислюється при кожному збереженні. Доступні всі поля документа як змінні.<br>
              Приклади: <code class="bg-muted px-1 rounded">qty * price</code>,
              <code class="bg-muted px-1 rounded">round(a + b, 2)</code>,
              <code class="bg-muted px-1 rounded">first_name + ' ' + last_name</code>
            </p>
          </div>
          <div v-if="field.formula" class="flex items-center gap-2 pt-1 pl-0.5">
            <Checkbox :model-value="!!field.read_only" @update:model-value="updateField('read_only', $event)" />
            <Label class="text-sm text-muted-foreground cursor-pointer">Read Only (рекомендовано)</Label>
          </div>
        </div>
      </template>

      <!-- AGGREGATE -->
      <template v-if="has('aggregate')">
        <Separator class="mb-3" />
        <div class="flex items-center justify-between mb-3">
          <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Aggregation</p>
          <span
            v-if="field.aggregate_function"
            class="text-[10px] font-mono text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-800 px-1.5 py-0.5 rounded"
          >∑ активна</span>
        </div>
        <div class="flex flex-col gap-3 mb-4">
          <div class="space-y-1.5">
            <Label class="text-sm">Функція</Label>
            <Select
              :model-value="field.aggregate_function ?? '__none__'"
              @update:model-value="updateField('aggregate_function', $event === '__none__' ? null : $event)"
            >
              <SelectTrigger><SelectValue placeholder="— без агрегації —" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">— без агрегації —</SelectItem>
                <SelectItem value="sum">sum — сума</SelectItem>
                <SelectItem value="count">count — кількість рядків</SelectItem>
                <SelectItem value="avg">avg — середнє</SelectItem>
                <SelectItem value="min">min — мінімум</SelectItem>
                <SelectItem value="max">max — максимум</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <template v-if="field.aggregate_function">
            <div class="space-y-1.5">
              <Label class="text-sm">Таблиця (TABLE поле)</Label>
              <Select
                :model-value="field.aggregate_table ?? ''"
                @update:model-value="updateField('aggregate_table', $event || null)"
              >
                <SelectTrigger><SelectValue placeholder="— оберіть TABLE поле —" /></SelectTrigger>
                <SelectContent>
                  <SelectItem v-for="tf in tableFields" :key="tf.fieldname" :value="tf.fieldname">
                    {{ tf.label || tf.fieldname }} ({{ tf.fieldname }})
                  </SelectItem>
                  <div v-if="!tableFields.length" class="px-2 py-1.5 text-xs text-muted-foreground">
                    Немає TABLE полів у цьому DocType
                  </div>
                </SelectContent>
              </Select>
            </div>
            <div v-if="field.aggregate_function !== 'count'" class="space-y-1.5">
              <Label class="text-sm">Поле дочірнього DocType</Label>
              <Input
                :model-value="field.aggregate_field ?? ''"
                placeholder="напр. amount"
                @update:model-value="updateField('aggregate_field', $event || null)"
              />
              <p class="text-[11px] text-muted-foreground">Fieldname числового поля у дочірньому DocType</p>
            </div>
          </template>
        </div>
      </template>

      <!-- OPTIONS: Select -->
      <template v-if="has('options')">
        <Separator class="mb-3" />
        <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Options</p>
        <div class="mb-4">
          <textarea
            :value="field.options ?? ''"
            rows="5"
            placeholder="Each option on a new line"
            class="w-full text-sm border border-input rounded-md px-2 py-1.5 bg-background focus:outline-none focus:ring-1 focus:ring-ring"
            @input="updateField('options', ($event.target as HTMLTextAreaElement).value)"
          />
        </div>
      </template>

      <!-- LINK: Linked DocType -->
      <template v-if="has('link')">
        <Separator class="mb-3" />
        <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Linked DocType</p>
        <div class="mb-4">
          <Select :model-value="field.options ?? ''" @update:model-value="updateField('options', $event)" @update:open="(o) => { if (!o) linkSearch = '' }">
            <SelectTrigger><SelectValue placeholder="— оберіть —" /></SelectTrigger>
            <SelectContent>
              <div class="px-2 pb-1">
                <input
                  v-model="linkSearch"
                  placeholder="Пошук..."
                  class="w-full h-7 px-2 text-sm rounded border border-input bg-background outline-none focus:ring-1 focus:ring-ring"
                  @keydown.stop
                />
              </div>
              <SelectItem v-for="opt in doctypeOptions" :key="opt" :value="opt">{{ opt }}</SelectItem>
              <div v-if="!doctypeOptions.length" class="px-2 py-1.5 text-xs text-muted-foreground">Нічого не знайдено</div>
            </SelectContent>
          </Select>
        </div>
      </template>

      <!-- LINK FILTERS -->
      <template v-if="has('link') && field.options">
        <div class="mb-4">
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

      <!-- TABLE: Child DocType -->
      <template v-if="has('table')">
        <Separator class="mb-3" />
        <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Child DocType</p>
        <div class="mb-4">
          <Select :model-value="field.options ?? ''" @update:model-value="updateField('options', $event)" @update:open="(o) => { if (!o) tableSearch = '' }">
            <SelectTrigger><SelectValue placeholder="— оберіть —" /></SelectTrigger>
            <SelectContent>
              <div class="px-2 pb-1">
                <input
                  v-model="tableSearch"
                  placeholder="Пошук..."
                  class="w-full h-7 px-2 text-sm rounded border border-input bg-background outline-none focus:ring-1 focus:ring-ring"
                  @keydown.stop
                />
              </div>
              <SelectItem v-for="opt in childDoctypeOptions" :key="opt" :value="opt">{{ opt }}</SelectItem>
              <div v-if="!childDoctypeOptions.length" class="px-2 py-1.5 text-xs text-muted-foreground">Нічого не знайдено</div>
            </SelectContent>
          </Select>
        </div>
      </template>
    </template>

    <!-- No selection -->
    <div v-else class="flex items-center justify-center h-32 text-muted-foreground text-sm">
      Оберіть поле для редагування
    </div>
  </div>
</template>
