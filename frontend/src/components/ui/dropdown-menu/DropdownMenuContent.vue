<script setup lang="ts">
import { inject, ref, computed } from 'vue'
import { useFloating, offset, flip, shift, autoUpdate } from '@floating-ui/vue'
import { onClickOutside } from '@vueuse/core'
import { cn } from '@/lib/utils'

const props = withDefaults(defineProps<{
  class?: string
  align?: 'start' | 'center' | 'end'
  side?: 'top' | 'bottom' | 'left' | 'right'
  sideOffset?: number
}>(), {
  align: 'start',
  side: 'bottom',
  sideOffset: 4,
})

const ctx = inject<any>('$dropdown')
const contentRef = ref<HTMLElement>()

const placement = computed(() => {
  const side = props.side
  const align = props.align
  if (align === 'center') return side
  return `${side}-${align}` as any
})

const reference = computed(() => ctx?.triggerEl.value ?? null)

const { floatingStyles } = useFloating(
  reference,
  contentRef,
  {
    placement,
    middleware: [offset(props.sideOffset), flip(), shift({ padding: 8 })],
    whileElementsMounted: autoUpdate,
  },
)

onClickOutside(contentRef, (e) => {
  const trigger = ctx?.triggerEl.value
  if (trigger && trigger.contains(e.target as Node)) return
  ctx?.close()
}, { capture: true })

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') ctx?.close()
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="ctx?.isOpen.value"
      ref="contentRef"
      data-slot="dropdown-menu-content"
      :style="floatingStyles"
      :class="cn(
        'bg-popover text-popover-foreground z-50 min-w-[8rem] overflow-hidden rounded-md border p-1 shadow-md',
        props.class,
      )"
      @keydown="onKeydown"
    >
      <slot />
    </div>
  </Teleport>
</template>
