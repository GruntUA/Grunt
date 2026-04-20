<script setup lang="ts">
import { inject, ref, computed, type Ref } from 'vue'
import { useFloating, autoUpdate, offset, flip, shift } from '@floating-ui/vue'
import { cn } from '@/lib/utils'

defineOptions({ inheritAttrs: false })

const props = withDefaults(defineProps<{
  side?: 'top' | 'bottom' | 'left' | 'right'
  sideOffset?: number
  class?: string
}>(), {
  side: 'top',
  sideOffset: 4,
})

interface TooltipCtx {
  referenceEl: Ref<Element | null>
  isOpen: Ref<boolean>
}

const ctx = inject<TooltipCtx>('$tooltip')
const floatingEl = ref<HTMLElement | null>(null)
const reference = computed(() => ctx?.referenceEl.value ?? null)

const { floatingStyles } = useFloating(
  reference,
  floatingEl,
  {
    placement: () => props.side,
    middleware: [offset(props.sideOffset), flip(), shift({ padding: 4 })],
    whileElementsMounted: autoUpdate,
  },
)
</script>

<template>
  <Teleport to="body">
    <div
      v-if="ctx?.isOpen.value"
      ref="floatingEl"
      data-slot="tooltip-content"
      :style="floatingStyles"
      :class="cn(
        'bg-foreground text-background z-50 w-fit rounded-md px-3 py-1.5 text-xs pointer-events-none',
        props.class,
      )"
    >
      <slot />
    </div>
  </Teleport>
</template>
