<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, ref, watch } from 'vue'
import { getLocalTimeZone, parseDate, type DateValue } from '@internationalized/date'
import { CalendarIcon, X } from '@lucide/vue'
import type { DocField, DocType, QuickFilter } from '@/types'
import { Calendar } from '@/components/ui/calendar'
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from '@/components/ui/input-group'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import LinkFilterInput from '@/components/fields/Link/FilterInput.vue'
import { docsApi } from '@/core/api'
import { formatDate, localeTag } from '@/core/datetime'

/**
 * Quick filters inline in the list toolbar. Every control is an InputGroup
 * whose trailing ✕ addon clears the value; the field label is the placeholder.
 */

const { t } = useI18n()

const props = defineProps<{
  defs: QuickFilter[]
  dt: DocType
  scope: 'list' | 'tree'
  modelValue: Record<string, string>
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: Record<string, string>): void
}>()

// Only show filters that are enabled for this scope AND have local mode.
// External mode filters are driven by scripts only - no UI control rendered.
const activeDefs = computed(() =>
  props.defs.filter(ff =>
    ff.enabled_in.includes(props.scope) && ff.on_change.mode !== 'external'
  ),
)

function getField(ff: QuickFilter): DocField | undefined {
  return props.dt.fields.find(f => f.fieldname === ff.field)
}

function getSelectOptions(ff: QuickFilter): { value: string, label: string }[] {
  // A Check field is filtered as Yes / No - '0' is a real filter, distinct from "any".
  if (ff.input_type === 'check') return [{ value: '1', label: t('Yes') }, { value: '0', label: t('No') }]
  if (ff.input_type === 'year') return yearOptions(ff)
  // Explicit options on the filter definition take priority over field.options
  const raw = ff.options?.length
    ? ff.options
    : String(getField(ff)?.options ?? '').split('\n').map(s => s.trim()).filter(Boolean)
  return raw.map(o => ({ value: o, label: o }))
}

function getLabel(ff: QuickFilter): string {
  return ff.label ?? getField(ff)?.label ?? ff.field
}

function getValue(ff: QuickFilter): string {
  return props.modelValue[ff.id] ?? ''
}

function onInput(ff: QuickFilter, value: string) {
  emit('update:modelValue', { ...props.modelValue, [ff.id]: value })
}

// Date
// Values are stored as YYYY-MM-DD; the calendar works with DateValue.
const openDateId = ref<string | null>(null)

function toDateValue(v: string): DateValue | undefined {
  try { return v ? parseDate(v) : undefined } catch { return undefined }
}

function dateLabel(v: string): string {
  const d = toDateValue(v)
  return d ? formatDate(d.toDate(getLocalTimeZone())) : ''
}

function onDatePick(ff: QuickFilter, d: DateValue | undefined) {
  onInput(ff, d ? d.toString() : '')
  openDateId.value = null
}

// Year
// Only the years present in the field's data are offered (newest first).
const fieldYears = ref<Record<string, number[]>>({})

function yearOptions(ff: QuickFilter): { value: string, label: string }[] {
  const years = [...(fieldYears.value[ff.id] ?? [])]
  // A year restored from saved view state stays pickable even if no row has it now.
  const picked = Number(getValue(ff))
  if (Number.isInteger(picked) && picked > 0 && !years.includes(picked)) {
    years.push(picked)
    years.sort((a, b) => b - a)
  }
  return years.map(y => ({ value: String(y), label: String(y) }))
}

watch(
  () => activeDefs.value.filter(ff => ff.input_type === 'year').map(ff => ff.id).join('|'),
  () => {
    for (const ff of activeDefs.value) {
      if (ff.input_type !== 'year' || ff.id in fieldYears.value) continue
      docsApi.getFieldYears(props.dt.name, ff.field)
        .then(years => { fieldYears.value = { ...fieldYears.value, [ff.id]: years } })
        .catch(() => {})
    }
  },
  { immediate: true },
)

// Link
// Link filters store the linked document's id; its title is kept here for display.
const linkTitles = ref<Record<string, string>>({})

function linkTitleKey(ff: QuickFilter, id = getValue(ff)): string {
  return `${ff.id}:${id}`
}

// The picker emits the id, then its title, before the new id comes back via props.
const pickedIds: Record<string, string> = {}

function onLinkPick(ff: QuickFilter, id: string) {
  pickedIds[ff.id] = id
  onInput(ff, id)
}

function onLinkTitle(ff: QuickFilter, title: string) {
  const id = pickedIds[ff.id]
  if (id && title) linkTitles.value = { ...linkTitles.value, [linkTitleKey(ff, id)]: title }
}

// A value restored from saved view state arrives without a title - look it up.
watch(
  () => activeDefs.value.filter(ff => ff.input_type === 'link' && getValue(ff)).map(ff => linkTitleKey(ff)).join('|'),
  () => {
    for (const ff of activeDefs.value) {
      const id = getValue(ff)
      const doctype = getField(ff)?.options
      const key = linkTitleKey(ff)
      if (ff.input_type !== 'link' || !id || !doctype || key in linkTitles.value) continue
      docsApi.linkSearch(String(doctype), '', { name: id }, 1)
        .then(([hit]) => { if (hit) linkTitles.value = { ...linkTitles.value, [key]: hit.title || hit.name } })
        .catch(() => {})
    }
  },
  { immediate: true },
)
</script>

<template>
  <div v-if="activeDefs.length" class="flex flex-wrap items-center gap-2">
    <template v-for="ff in activeDefs" :key="ff.id">
      <!-- Link: pick the linked document (the filter compares its id, not typed text); has its own ✕ -->
      <div
        v-if="ff.input_type === 'link' && getField(ff)"
        class="w-[200px]"
      >
        <LinkFilterInput
          :field="getField(ff)!"
          :model-value="getValue(ff)"
          :display-value="linkTitles[linkTitleKey(ff)] ?? ''"
          :op="ff.operator"
          :placeholder="getLabel(ff)"
          @update:model-value="(v: string) => onLinkPick(ff, v)"
          @update:display-value="(v: string) => onLinkTitle(ff, v)"
        />
      </div>

      <InputGroup
        v-else
        class="w-auto has-[[data-slot=select-trigger]:focus-visible]:border-ring has-[[data-slot=select-trigger]:focus-visible]:ring-3 has-[[data-slot=select-trigger]:focus-visible]:ring-ring/50"
      >
        <!-- Select / Check / Year: the chevron gives way to ✕ once a value is chosen -->
        <Select
          v-if="ff.input_type === 'select' || ff.input_type === 'check' || ff.input_type === 'year'"
          :model-value="getValue(ff)"
          @update:model-value="(v: unknown) => onInput(ff, String(v ?? ''))"
        >
          <SelectTrigger
            :id="`ff-${ff.id}`"
            :aria-label="getLabel(ff)"
            class="h-full min-w-[150px] flex-1 border-0 bg-transparent shadow-none focus-visible:ring-0 dark:bg-transparent"
            :class="getValue(ff) && '[&>svg:last-child]:hidden'"
          >
            <SelectValue :placeholder="getLabel(ff)" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="opt in getSelectOptions(ff)" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
          </SelectContent>
        </Select>

        <!-- Date: popover calendar -->
        <Popover
          v-else-if="ff.input_type === 'date'"
          :open="openDateId === ff.id"
          @update:open="(o: boolean) => { openDateId = o ? ff.id : null }"
        >
          <PopoverTrigger as-child>
            <button
              :id="`ff-${ff.id}`"
              type="button"
              data-slot="input-group-control"
              class="flex h-full w-[150px] items-center gap-2 rounded-md px-3 text-left outline-none"
              :class="!getValue(ff) && 'text-muted-foreground'"
            >
              <CalendarIcon class="size-4 shrink-0 text-muted-foreground" />
              <span class="truncate">{{ dateLabel(getValue(ff)) || getLabel(ff) }}</span>
            </button>
          </PopoverTrigger>
          <PopoverContent class="w-auto p-0" align="start">
            <Calendar
              :model-value="toDateValue(getValue(ff))"
              :locale="localeTag()"
              initial-focus
              @update:model-value="(d) => onDatePick(ff, d as DateValue | undefined)"
            />
          </PopoverContent>
        </Popover>

        <!-- Number / text -->
        <InputGroupInput
          v-else
          :id="`ff-${ff.id}`"
          :type="ff.input_type === 'number' ? 'number' : 'text'"
          :model-value="getValue(ff)"
          :placeholder="getLabel(ff)"
          class="h-full"
          :class="ff.input_type === 'number' ? 'w-[130px]' : 'w-[150px]'"
          @update:model-value="(v: string | number) => onInput(ff, String(v))"
        />

        <InputGroupAddon v-if="getValue(ff)" align="inline-end">
          <InputGroupButton
            size="icon-xs"
            :aria-label="t('Clear «{label}»', { label: getLabel(ff) })"
            :title="t('Clear «{label}»', { label: getLabel(ff) })"
            @click="onInput(ff, '')"
          >
            <X />
          </InputGroupButton>
        </InputGroupAddon>
      </InputGroup>
    </template>
  </div>
</template>
