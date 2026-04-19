<script setup lang="ts">
import { inject } from 'vue'
import { Check } from '@lucide/vue'
import { cn } from '@/lib/utils'

const props = defineProps<{
  class?: string
  checked?: boolean
  disabled?: boolean
}>()
const emit = defineEmits<{
  'update:checked': [value: boolean]
  select: [event: Event]
}>()

const ctx = inject<any>('$dropdown')

function handleClick() {
  if (props.disabled) return
  emit('update:checked', !props.checked)
  const selectEvent = new Event('select', { cancelable: true })
  emit('select', selectEvent)
  if (!selectEvent.defaultPrevented) {
    ctx?.close()
  }
}
</script>

<template>
  <div
    role="menuitemcheckbox"
    :aria-checked="checked"
    data-slot="dropdown-menu-checkbox-item"
    :data-disabled="disabled || undefined"
    :class="cn(
      'relative flex cursor-default select-none items-center gap-2 rounded-sm py-1.5 pl-8 pr-2 text-sm outline-none transition-colors hover:bg-accent hover:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50',
      props.class,
    )"
    @click="handleClick"
  >
    <span class="pointer-events-none absolute left-2 flex size-3.5 items-center justify-center">
      <Check v-if="checked" class="size-4" />
    </span>
    <slot />
  </div>
</template>
