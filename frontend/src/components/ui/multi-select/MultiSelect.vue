<script setup lang="ts">
import { ref, computed, nextTick, watch } from 'vue'
import { ChevronDown, Search } from '@lucide/vue'
import { cn } from '@/lib/utils'
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
const search = ref('')
const searchEl = ref<HTMLInputElement | null>(null)

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

const selectedText = computed(() => selectedLabels.value.join(', '))

const filteredOptions = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return props.options
  return props.options.filter(o => optLabel(o).toLowerCase().includes(q))
})

watch(isOpen, (open) => {
  if (open) {
    nextTick(() => searchEl.value?.focus())
  } else {
    search.value = ''
  }
})

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
      'border-input flex h-9 w-full items-center justify-between gap-2 rounded-md border bg-transparent px-3 py-2 text-sm shadow-xs outline-none transition-[color,box-shadow] hover:bg-accent/50 focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-3 disabled:cursor-not-allowed disabled:opacity-50',
      !selectedLabels.length && 'text-muted-foreground',
      props.class,
    )"
    @click="toggle"
  >
    <span class="truncate text-left">{{ selectedLabels.length ? selectedText : placeholder }}</span>
    <ChevronDown class="size-4 shrink-0 opacity-50" />
  </button>

  <Popover v-model:open="isOpen">
    <PopoverAnchor :reference="anchorEl ?? undefined" />
    <PopoverContent class="w-(--reka-popper-anchor-width) p-1">
      <div class="flex items-center gap-2 border-b px-2 pb-1.5 pt-1">
        <Search class="size-4 shrink-0 opacity-50" />
        <input
          ref="searchEl"
          v-model="search"
          type="text"
          placeholder="Пошук…"
          class="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
        >
      </div>
      <div class="mt-1 max-h-64 overflow-y-auto flex flex-col gap-0.5">
        <label
          v-for="opt in filteredOptions"
          :key="optValue(opt)"
          class="flex items-center gap-2 rounded-sm px-2 py-1.5 hover:bg-accent hover:text-accent-foreground transition-colors cursor-pointer"
        >
          <Checkbox :model-value="modelValue.includes(optValue(opt))" @update:model-value="toggleValue(optValue(opt))" />
          <span class="truncate">{{ optLabel(opt) }}</span>
        </label>
        <p v-if="!options.length" class="px-2 py-3 text-center text-muted-foreground">Немає варіантів</p>
        <p v-else-if="!filteredOptions.length" class="px-2 py-3 text-center text-muted-foreground">Нічого не знайдено</p>
      </div>
    </PopoverContent>
  </Popover>
</template>
