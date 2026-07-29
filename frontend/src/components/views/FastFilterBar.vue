<script setup lang="ts">
import { computed } from 'vue'
import type { DocField, DocType, FastFilter } from '@/types'

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
        <input
          v-if="ff.input_type === 'date'"
          :id="`ff-${ff.id}`"
          type="date"
          :value="getValue(ff)"
          @input="onInput(ff, ($event.target as HTMLInputElement).value)"
          class="h-7 rounded-md border border-border/60 bg-background px-2 text-xs text-foreground shadow-sm
                 focus-visible:outline-none focus:border-primary/40 focus:ring-1 focus:ring-primary/30
               transition-all"
             :class="props.variant === 'quick' ? 'h-9 w-[160px] rounded-lg bg-muted/30 placeholder:text-muted-foreground/80' : 'w-[140px]'"
             :placeholder="props.variant === 'quick' ? getLabel(ff) : ''"
        />

        <!-- Select input -->
        <select
          v-else-if="ff.input_type === 'select'"
          :id="`ff-${ff.id}`"
          :value="getValue(ff)"
          @change="onInput(ff, ($event.target as HTMLSelectElement).value)"
          class="h-7 rounded-md border border-border/60 bg-background px-2 text-xs text-foreground shadow-sm
                 focus-visible:outline-none focus:border-primary/40 focus:ring-1 focus:ring-primary/30
                 transition-all"
          :class="props.variant === 'quick' ? 'h-9 min-w-[160px] rounded-lg bg-muted/30' : ''"
        >
          <option value="">{{ props.variant === 'quick' ? getLabel(ff) : '— Будь-який —' }}</option>
          <option v-for="opt in getSelectOptions(ff)" :key="opt" :value="opt">{{ opt }}</option>
        </select>

        <!-- Number input -->
        <input
          v-else-if="ff.input_type === 'number'"
          :id="`ff-${ff.id}`"
          type="number"
          :value="getValue(ff)"
          @input="onInput(ff, ($event.target as HTMLInputElement).value)"
          class="h-7 rounded-md border border-border/60 bg-background px-2 text-xs text-foreground shadow-sm
                 focus-visible:outline-none focus:border-primary/40 focus:ring-1 focus:ring-primary/30
               transition-all"
             :class="props.variant === 'quick' ? 'h-9 w-[140px] rounded-lg bg-muted/30 placeholder:text-muted-foreground/80' : 'w-[100px]'"
             :placeholder="props.variant === 'quick' ? getLabel(ff) : ''"
        />

        <!-- Checkbox -->
        <input
          v-else-if="ff.input_type === 'check'"
          :id="`ff-${ff.id}`"
          type="checkbox"
          :checked="getValue(ff) === '1'"
          @change="onInput(ff, ($event.target as HTMLInputElement).checked ? '1' : '0')"
          class="rounded border-border/60 accent-primary"
          :class="props.variant === 'quick' ? 'size-5' : 'size-4'"
        />

        <!-- Text / link / fallback -->
        <input
          v-else
          :id="`ff-${ff.id}`"
          type="text"
          :value="getValue(ff)"
          @input="onInput(ff, ($event.target as HTMLInputElement).value)"
          class="h-7 rounded-md border border-border/60 bg-background px-2 text-xs text-foreground shadow-sm
                 focus-visible:outline-none focus:border-primary/40 focus:ring-1 focus:ring-primary/30
               transition-all"
             :class="props.variant === 'quick' ? 'h-9 w-[160px] rounded-lg bg-muted/30 placeholder:text-muted-foreground/80' : 'w-[160px]'"
             :placeholder="props.variant === 'quick' ? getLabel(ff) : '...'"
        />

        <!-- Clear button -->
        <button
          v-if="getValue(ff)"
          type="button"
          class="text-muted-foreground hover:text-foreground transition-colors"
          @click="onInput(ff, '')"
          :title="`Очистити «${getLabel(ff)}»`"
        >
          <svg class="size-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <path d="M18 6 6 18M6 6l12 12"/>
          </svg>
        </button>
      </div>

      <!-- Separator between filters -->
      <div
        v-if="props.variant !== 'quick' && activeDefs.indexOf(ff) < activeDefs.length - 1"
        class="h-4 w-px bg-border/40"
      />
    </template>
  </div>
</template>
