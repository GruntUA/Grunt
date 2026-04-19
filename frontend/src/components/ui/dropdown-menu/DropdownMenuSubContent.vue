<script setup lang="ts">
import { inject, ref, computed } from 'vue'
import { useFloating, offset, flip, shift, autoUpdate } from '@floating-ui/vue'
import { cn } from '@/lib/utils'

const props = defineProps<{ class?: string }>()

const subCtx = inject<any>('$dropdownSub')
const contentRef = ref<HTMLElement>()

const reference = computed(() => subCtx?.triggerEl.value ?? null)

const { floatingStyles } = useFloating(
  reference,
  contentRef,
  {
    placement: 'right-start',
    middleware: [offset(2), flip(), shift({ padding: 8 })],
    whileElementsMounted: autoUpdate,
  },
)
</script>

<template>
  <Teleport to="body">
    <div
      v-if="subCtx?.isOpen.value"
      ref="contentRef"
      data-slot="dropdown-menu-sub-content"
      :style="floatingStyles"
      :class="cn(
        'bg-popover text-popover-foreground z-50 min-w-[8rem] overflow-hidden rounded-md border p-1 shadow-lg',
        props.class,
      )"
      @mouseenter="subCtx?.open()"
      @mouseleave="subCtx?.close()"
    >
      <slot />
    </div>
  </Teleport>
</template>
