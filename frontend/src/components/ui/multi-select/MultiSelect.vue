<script setup lang="ts">
import { ref, computed } from 'vue'
import { ChevronDown } from '@lucide/vue'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Popover, PopoverAnchor, PopoverContent } from '@/components/ui/popover'
interface OptionObj { [key: string]: unknown }

const props = withDefaults(defineProps<{
  modelValue: string[]
  options: (string | OptionObj)[]
  optionLabel?: string
  optionValue?: string
  placeholder?: string
  disabled?: boolean
  class?: string
}>(), {
  placeholder: '— оберіть —',
})

const emit = defineEmits<{ 'update:modelValue': [value: string[]] }>()

const isOpen = ref(false)
const anchorEl = ref<HTMLElement | null>(null)

function optValue(opt: string | OptionObj): string {
  return props.optionValue && typeof opt === 'object' ? String((opt as OptionObj)[props.optionValue]) : String(opt)
}
function optLabel(opt: string | OptionObj): string {
  return props.optionLabel && typeof opt === 'object' ? String((opt as OptionObj)[props.optionLabel]) : String(opt)
}

const selectedLabels = computed(() =>
  props.options
    .filter(o => props.modelValue.includes(optValue(o)))
    .map(o => optLabel(o))
)

function toggle(event: Event) {
  if (props.disabled) return
  if (isOpen.value) { isOpen.value = false; return }
  anchorEl.value = event.currentTarget as HTMLElement
  isOpen.value = true
}

function toggleValue(v: string) {
  const next = props.modelValue.includes(v)
    ? props.modelValue.filter(x => x !== v)
    : [...props.modelValue, v]
  emit('update:modelValue', next)
}
</script>

<template>
  <button
    type="button"
    :disabled="disabled"
    :class="cn(
      'border-input flex h-9 w-fit items-center justify-between gap-2 rounded-md border bg-transparent px-3 py-2 text-sm shadow-xs outline-none transition-[color,box-shadow] hover:bg-accent/50 focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-3 disabled:cursor-not-allowed disabled:opacity-50',
      !selectedLabels.length && 'text-muted-foreground',
      props.class,
    )"
    @click="toggle"
  >
    <span class="flex-1 min-w-0 flex items-center gap-1 flex-wrap">
      <span v-if="!selectedLabels.length" class="truncate">{{ placeholder }}</span>
      <template v-else-if="selectedLabels.length <= 2">
        <Badge v-for="label in selectedLabels" :key="label" variant="secondary" class="text-xs">{{ label }}</Badge>
      </template>
      <Badge v-else variant="secondary" class="text-xs">{{ selectedLabels.length }} вибрано</Badge>
    </span>
    <ChevronDown class="size-4 shrink-0 opacity-50" />
  </button>

  <Popover v-model:open="isOpen">
    <PopoverAnchor :reference="anchorEl ?? undefined" />
    <PopoverContent class="w-(--reka-popper-anchor-width) p-1">
      <div class="max-h-64 overflow-y-auto flex flex-col gap-0.5">
        <label
          v-for="opt in options"
          :key="optValue(opt)"
          class="flex items-center gap-2 rounded-sm px-2 py-1.5 hover:bg-accent hover:text-accent-foreground transition-colors cursor-pointer"
        >
          <Checkbox :model-value="modelValue.includes(optValue(opt))" @update:model-value="toggleValue(optValue(opt))" />
          <span class="truncate">{{ optLabel(opt) }}</span>
        </label>
        <p v-if="!options.length" class="px-2 py-3 text-center text-muted-foreground">Немає варіантів</p>
      </div>
    </PopoverContent>
  </Popover>
</template>
