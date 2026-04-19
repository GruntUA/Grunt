<script setup lang="ts">
import { inject } from 'vue'
import { cn } from '@/lib/utils'

const props = withDefaults(defineProps<{
  class?: string
  inset?: boolean
  variant?: 'default' | 'destructive'
  disabled?: boolean
}>(), {
  variant: 'default',
})

const emit = defineEmits<{ select: [event: Event] }>()

const ctx = inject<any>('$dropdown')

function handleClick() {
  if (props.disabled) return
  const selectEvent = new Event('select', { cancelable: true })
  emit('select', selectEvent)
  if (!selectEvent.defaultPrevented) {
    ctx?.close()
  }
}
</script>

<template>
  <div
    role="menuitem"
    data-slot="dropdown-menu-item"
    :data-inset="inset || undefined"
    :data-variant="variant"
    :data-disabled="disabled || undefined"
    :class="cn(
      'relative flex cursor-default select-none items-center gap-2 rounded-sm px-2 py-1.5 text-sm outline-none transition-colors hover:bg-accent hover:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50 data-[inset]:pl-8 data-[variant=destructive]:text-destructive data-[variant=destructive]:hover:bg-destructive/10',
      props.class,
    )"
    @click="handleClick"
  >
    <slot />
  </div>
</template>
