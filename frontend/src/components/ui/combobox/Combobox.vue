<script setup lang="ts">
import { ref, computed } from 'vue'
import { ChevronDown } from '@lucide/vue'
import { cn } from '@/lib/utils'

const props = withDefaults(defineProps<{
  modelValue: string
  options: string[]
  placeholder?: string
  emptyMessage?: string
  disabled?: boolean
  class?: string
}>(), {
  placeholder: '— оберіть —',
  emptyMessage: 'Нічого не знайдено',
})

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const isOpen = ref(false)
const anchorEl = ref<HTMLElement | null>(null)
const search = ref('')

function toggle(event: Event) {
  if (props.disabled) return
  if (isOpen.value) { isOpen.value = false; return }
  anchorEl.value = event.currentTarget as HTMLElement
  search.value = ''
  isOpen.value = true
}

function select(opt: string) {
  emit('update:modelValue', opt)
  isOpen.value = false
}

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return props.options
  return props.options.filter(o => o.toLowerCase().includes(q))
})
</script>

<template>
  <button
    type="button"
    :disabled="disabled"
    :class="cn(
      'border-input flex h-9 w-fit items-center justify-between gap-2 rounded-md border bg-transparent px-3 py-2 text-sm shadow-xs outline-none transition-[color,box-shadow] hover:bg-accent/50 focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-3 disabled:cursor-not-allowed disabled:opacity-50',
      !modelValue && 'text-muted-foreground',
      props.class,
    )"
    @click="toggle"
  >
    <span class="truncate">{{ modelValue || placeholder }}</span>
    <ChevronDown class="size-4 shrink-0 opacity-50" />
  </button>

  <Popover v-model:open="isOpen">
    <PopoverAnchor :reference="anchorEl ?? undefined" />
    <PopoverContent class="w-(--reka-popper-anchor-width) p-0">
      <div class="p-1.5 border-b border-border">
        <input
          v-model="search"
          autofocus
          placeholder="Пошук..."
          class="w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground px-1.5 py-1"
        />
      </div>
      <div class="max-h-64 overflow-y-auto p-1">
        <button
          v-for="opt in filtered"
          :key="opt"
          type="button"
          class="w-full rounded-sm px-2 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground transition-colors"
          :class="opt === modelValue ? 'bg-accent/60 font-medium' : ''"
          @click="select(opt)"
        >{{ opt }}</button>
        <p v-if="!filtered.length" class="px-2 py-3 text-center text-sm text-muted-foreground">{{ emptyMessage }}</p>
      </div>
    </PopoverContent>
  </Popover>
</template>
