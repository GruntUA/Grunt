<script setup lang="ts">
import { inject } from 'vue'
import { cn } from '@/lib/utils'

const props = defineProps<{
  value: string
  class?: string
  disabled?: boolean
}>()
const emit = defineEmits<{ select: [event: Event] }>()

const ctx = inject<any>('$dropdown')
const radioCtx = inject<any>('$dropdownRadio')
</script>

<template>
  <div
    role="menuitemradio"
    :aria-checked="radioCtx?.modelValue?.value === props.value"
    data-slot="dropdown-menu-radio-item"
    :data-disabled="disabled || undefined"
    :class="cn(
      'relative flex cursor-default select-none items-center gap-2 rounded-sm py-1.5 pl-8 pr-2 text-sm outline-none transition-colors hover:bg-accent hover:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50',
      props.class,
    )"
    @click="!disabled && (radioCtx?.setValue(props.value), ctx?.close())"
  >
    <span class="pointer-events-none absolute left-2 flex size-3.5 items-center justify-center">
      <span v-if="radioCtx?.modelValue?.value === props.value" class="size-2 rounded-full bg-current" />
    </span>
    <slot />
  </div>
</template>
