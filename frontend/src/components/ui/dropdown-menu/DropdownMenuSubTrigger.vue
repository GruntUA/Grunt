<script setup lang="ts">
import { inject, ref, onMounted } from 'vue'
import { ChevronRight } from '@lucide/vue'
import { cn } from '@/lib/utils'

const props = defineProps<{
  class?: string
  inset?: boolean
}>()

const subCtx = inject<any>('$dropdownSub')
const triggerRef = ref<HTMLElement>()

onMounted(() => {
  if (subCtx && triggerRef.value) subCtx.triggerEl.value = triggerRef.value
})
</script>

<template>
  <div
    ref="triggerRef"
    data-slot="dropdown-menu-sub-trigger"
    :data-inset="inset || undefined"
    :class="cn(
      'flex cursor-default select-none items-center gap-2 rounded-sm px-2 py-1.5 text-sm outline-none transition-colors hover:bg-accent hover:text-accent-foreground data-[inset]:pl-8',
      props.class,
    )"
    @mouseenter="subCtx?.open()"
    @mouseleave="subCtx?.close()"
    @click="subCtx?.open()"
  >
    <slot />
    <ChevronRight class="ml-auto size-4" />
  </div>
</template>
