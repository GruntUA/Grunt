<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { inject, ref, computed } from 'vue'
import { useFloating, offset, flip, shift, autoUpdate } from '@floating-ui/vue'
import { onClickOutside } from '@vueuse/core'
import { cn } from '@/lib/utils'

const props = withDefaults(defineProps<{
  class?: HTMLAttributes['class']
  align?: 'start' | 'center' | 'end'
  side?: 'top' | 'right' | 'bottom' | 'left'
  sideOffset?: number
  alignOffset?: number
}>(), {
  align: 'center',
  side: 'bottom',
  sideOffset: 4,
  alignOffset: 0,
})

const ctx = inject<{
  isOpen: { value: boolean }
  triggerEl: { value: HTMLElement | null }
  close: () => void
}>('$popover')

const placement = computed(() => {
  const s = props.side
  const a = props.align
  return (a === 'center' ? s : `${s}-${a}`) as any
})

const middleware = computed(() => [
  offset({ mainAxis: props.sideOffset, alignmentAxis: props.alignOffset }),
  flip(),
  shift({ padding: 8 }),
])

const reference = computed(() => ctx?.triggerEl.value ?? null)
const contentRef = ref<HTMLElement | null>(null)

const { floatingStyles } = useFloating(reference, contentRef, {
  placement,
  middleware,
  whileElementsMounted: autoUpdate,
})

onClickOutside(contentRef, () => ctx?.close(), { ignore: [reference] })
</script>

<template>
  <Teleport to="body">
    <div
      v-if="ctx?.isOpen.value"
      ref="contentRef"
      data-slot="popover-content"
      :style="floatingStyles"
      :class="cn(
        'bg-popover text-popover-foreground z-50 w-72 rounded-md border p-4 shadow-md outline-none',
        props.class
      )"
    >
      <slot />
    </div>
  </Teleport>
</template>
