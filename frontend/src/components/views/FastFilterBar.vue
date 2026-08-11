<script setup lang="ts">
import { computed } from 'vue'
import { X } from '@lucide/vue'
import type { DocField, DocType, FastFilter } from '@/types'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'

const props = defineProps<{
  defs: FastFilter[]
  dt: DocType
  scope: 'list' | 'tree'
  modelValue: Record<string, string>
  variant?: 'default' | 'quick'
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: Record<string, string>): void
}>()

// Only show filters that are enabled for this scope AND have local mode.
// External mode filters are driven by scripts only — no UI control rendered.
const activeDefs = computed(() =>
  props.defs.filter(ff =>
    ff.enabled_in.includes(props.scope) && ff.on_change.mode !== 'external'
  ),
)

function getField(ff: FastFilter): DocField | undefined {
  return props.dt.fields.find(f => f.fieldname === ff.field)
}

function getSelectOptions(ff: FastFilter): string[] {
  // Explicit options on the filter definition take priority over field.options
  if (ff.options?.length) return ff.options
  const field = getField(ff)
  if (!field?.options) return []
  return String(field.options).split('\n').map(s => s.trim()).filter(Boolean)
}

function getLabel(ff: FastFilter): string {
  return ff.label ?? getField(ff)?.label ?? ff.field
}

function getValue(ff: FastFilter): string {
  return props.modelValue[ff.id] ?? ''
}

function onInput(ff: FastFilter, value: string) {
  emit('update:modelValue', { ...props.modelValue, [ff.id]: value })
}
</script>

<template>
  <div
    v-if="activeDefs.length"
    class="flex flex-wrap items-center gap-2 px-1 py-1"
  >
    <template v-for="ff in activeDefs" :key="ff.id">
      <div class="flex items-center gap-1.5">
        <label
          v-if="props.variant !== 'quick'"
          :for="`ff-${ff.id}`"
          class="text-xs font-medium text-muted-foreground whitespace-nowrap"
        >
          {{ getLabel(ff) }}
        </label>

        <!-- Date input -->
        <Input
          v-if="ff.input_type === 'date'"
          :id="`ff-${ff.id}`"
          type="date"
          :model-value="getValue(ff)"
          @update:model-value="(v: string | number) => onInput(ff, String(v))"
          class="h-7 text-xs"
          :class="props.variant === 'quick' ? 'w-[150px]' : 'w-[140px]'"
          :placeholder="props.variant === 'quick' ? getLabel(ff) : ''"
        />

        <!-- Select input -->
        <Select
          v-else-if="ff.input_type === 'select'"
          :model-value="getValue(ff) || '__any__'"
          @update:model-value="(v: unknown) => onInput(ff, v === '__any__' ? '' : String(v ?? ''))"
        >
          <SelectTrigger :id="`ff-${ff.id}`" size="sm" class="h-7 text-xs" :class="props.variant === 'quick' ? 'min-w-[150px]' : ''">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__any__">{{ props.variant === 'quick' ? getLabel(ff) : '— Будь-який —' }}</SelectItem>
            <SelectItem v-for="opt in getSelectOptions(ff)" :key="opt" :value="opt">{{ opt }}</SelectItem>
          </SelectContent>
        </Select>

        <!-- Number input -->
        <Input
          v-else-if="ff.input_type === 'number'"
          :id="`ff-${ff.id}`"
          type="number"
          :model-value="getValue(ff)"
          @update:model-value="(v: string | number) => onInput(ff, String(v))"
          class="h-7 text-xs"
          :class="props.variant === 'quick' ? 'w-[130px]' : 'w-[100px]'"
          :placeholder="props.variant === 'quick' ? getLabel(ff) : ''"
        />

        <!-- Checkbox -->
        <Checkbox
          v-else-if="ff.input_type === 'check'"
          :id="`ff-${ff.id}`"
          :model-value="getValue(ff) === '1'"
          @update:model-value="(v: boolean | 'indeterminate') => onInput(ff, v === true ? '1' : '0')"
        />

        <!-- Text / link / fallback -->
        <Input
          v-else
          :id="`ff-${ff.id}`"
          type="text"
          :model-value="getValue(ff)"
          @update:model-value="(v: string | number) => onInput(ff, String(v))"
          class="h-7 text-xs"
          :class="props.variant === 'quick' ? 'w-[150px]' : 'w-[160px]'"
          :placeholder="props.variant === 'quick' ? getLabel(ff) : '...'"
        />

        <!-- Clear button -->
        <Button
          v-if="getValue(ff)"
          variant="ghost" size="icon" class="size-5"
          @click="onInput(ff, '')"
          :title="`Очистити «${getLabel(ff)}»`"
        >
          <X class="size-3" />
        </Button>
      </div>

      <!-- Separator between filters -->
      <Separator
        v-if="props.variant !== 'quick' && activeDefs.indexOf(ff) < activeDefs.length - 1"
        orientation="vertical" class="h-4"
      />
    </template>
  </div>
</template>
