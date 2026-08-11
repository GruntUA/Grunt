<script setup lang="ts">
import { computed } from 'vue'
import { CircleDot, Plus, X } from '@lucide/vue'
import type { StatusIndicator } from '@/types'
import { useBuilderFields } from '@/core/composables/useBuilderFields'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'

const { builder, dataFields } = useBuilderFields()

const hasStatus = computed(() => !!builder.doctype?.status_config)
const statusField = computed(() => builder.doctype?.status_config?.field ?? '')
const statusIndicators = computed(() => builder.doctype?.status_config?.indicators ?? [])

const statusCandidateFields = computed(() =>
  dataFields.value.filter((f) => ['Select', 'Data', 'Text', 'Int'].includes(f.fieldtype)),
)

const statusColors = [
  'default',
  'secondary',
  'success',
  'info',
  'warn',
  'danger',
  'contrast',
] as const

const statusColorDotClass: Record<string, string> = {
  default: 'bg-slate-400',
  secondary: 'bg-slate-500',
  success: 'bg-green-500',
  info: 'bg-blue-500',
  warn: 'bg-amber-500',
  danger: 'bg-red-500',
  contrast: 'bg-zinc-900 dark:bg-zinc-100',
}

function getSelectOptions(fieldname: string): string[] {
  const f = dataFields.value.find((ff) => ff.fieldname === fieldname)
  if (!f || f.fieldtype !== 'Select' || !f.options) return []
  return f.options.split('\n').map((o) => o.trim()).filter(Boolean)
}

const selectFields = computed(() => dataFields.value.filter((f) => f.fieldtype === 'Select'))

function toggleStatus(enabled: boolean) {
  if (enabled) {
    const first = selectFields.value[0] ?? statusCandidateFields.value[0]
    const fieldname = first?.fieldname ?? ''
    const options = getSelectOptions(fieldname)
    const indicators: StatusIndicator[] = options.map((val, i) => ({
      value: val,
      color: statusColors[i % statusColors.length],
      icon: null,
      label: null,
    }))
    builder.updateDocType({ status_config: { field: fieldname, indicators } })
  } else {
    builder.updateDocType({ status_config: null })
  }
}

function updateStatusField(fieldname: string | number | bigint | Record<string, unknown> | null) {
  if (!builder.doctype?.status_config) return
  const fname = String(fieldname)
  const options = getSelectOptions(fname)
  const existing = builder.doctype.status_config.indicators
  const existingMap = new Map(existing.map((ind) => [ind.value, ind]))
  const indicators: StatusIndicator[] =
    options.length > 0
      ? options.map(
          (val, i) =>
            existingMap.get(val) ?? {
              value: val,
              color: statusColors[i % statusColors.length],
              icon: null,
              label: null,
            },
        )
      : existing
  builder.updateDocType({ status_config: { field: fname, indicators } })
}

function updateIndicator(index: number, patch: Partial<StatusIndicator>) {
  if (!builder.doctype?.status_config) return
  const indicators = [...builder.doctype.status_config.indicators]
  indicators[index] = { ...indicators[index], ...patch }
  builder.updateDocType({ status_config: { ...builder.doctype.status_config, indicators } })
}

function addIndicator() {
  if (!builder.doctype?.status_config) return
  const indicators = [
    ...builder.doctype.status_config.indicators,
    { value: '', color: 'secondary', icon: null, label: null },
  ]
  builder.updateDocType({ status_config: { ...builder.doctype.status_config, indicators } })
}

function removeIndicator(index: number) {
  if (!builder.doctype?.status_config) return
  const indicators = builder.doctype.status_config.indicators.filter((_, i) => i !== index)
  builder.updateDocType({ status_config: { ...builder.doctype.status_config, indicators } })
}
</script>

<template>
  <div v-if="builder.doctype" class="rounded-lg border border-border bg-card shadow-sm overflow-hidden">
    <div class="flex items-center justify-between px-4 py-3 bg-muted/40 border-b border-border">
      <div class="flex items-center gap-2.5">
        <CircleDot class="size-4 text-muted-foreground" />
        <h3 class="text-sm font-semibold text-foreground">Відображення: Статуси</h3>
        <span
          v-if="hasStatus"
          class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-500/15 text-green-700 dark:text-green-400"
        >Увімкнено</span>
      </div>
      <Switch :model-value="hasStatus" @update:model-value="toggleStatus" />
    </div>
    <div v-if="builder.doctype.status_config" class="p-4 space-y-4">
      <!-- Status field selector -->
      <div class="flex flex-col gap-1.5">
        <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Поле статусу *</label>
        <Select :model-value="statusField" @update:model-value="updateStatusField">
          <SelectTrigger class="h-8 text-xs">
            <SelectValue placeholder="Оберіть поле" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="opt in statusCandidateFields.map((f) => ({ value: f.fieldname, label: `${f.label} (${f.fieldtype})` }))" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <!-- Indicators list -->
      <div class="space-y-2">
        <div class="flex items-center justify-between">
          <label class="text-xs font-medium text-muted-foreground uppercase tracking-wide">Індикатори</label>
          <Button variant="outline" size="sm" class="h-7 px-2.5 text-xs gap-1" @click="addIndicator">
            <Plus class="size-3" />
            Додати
          </Button>
        </div>

        <div
          v-for="(ind, idx) in statusIndicators"
          :key="idx"
          class="flex items-center gap-3 p-2.5 border border-border rounded-md bg-muted/20"
        >
          <div
            class="size-3.5 rounded-full shrink-0 ring-1 ring-black/10"
            :class="statusColorDotClass[ind.color] || statusColorDotClass.secondary"
          />
          <Input
            :model-value="ind.value"
            placeholder="Значення"
            class="h-7 text-xs flex-1 min-w-0"
            @update:model-value="updateIndicator(idx, { value: String($event) })"
          />
          <Select :model-value="ind.color" @update:model-value="updateIndicator(idx, { color: String($event) })">
            <SelectTrigger class="h-7 text-xs w-32 shrink-0">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="opt in [...statusColors]" :key="opt" :value="opt">{{ opt }}</SelectItem>
            </SelectContent>
          </Select>
          <Input
            :model-value="ind.icon ?? ''"
            placeholder="Іконка"
            class="h-7 text-xs w-24 shrink-0"
            title="Назва іконки Lucide (опціонально)"
            @update:model-value="updateIndicator(idx, { icon: String($event) || null })"
          />
          <Input
            :model-value="ind.label ?? ''"
            placeholder="Мітка"
            class="h-7 text-xs w-24 shrink-0"
            title="Відображувана мітка (за замовчуванням = значення)"
            @update:model-value="updateIndicator(idx, { label: String($event) || null })"
          />
          <button
            class="text-muted-foreground hover:text-destructive transition-colors shrink-0"
            @click="removeIndicator(idx)"
          >
            <X class="size-3.5" />
          </button>
        </div>

        <p v-if="statusIndicators.length === 0" class="text-xs text-muted-foreground italic">
          Немає індикаторів. Оберіть Select поле — варіанти додадуться автоматично.
        </p>
      </div>
    </div>
  </div>
</template>
