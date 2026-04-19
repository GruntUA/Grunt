<script setup lang="ts">
import { inject, ref, type Ref } from 'vue'

defineProps<{ asChild?: boolean }>()

interface TooltipCtx {
  referenceEl: Ref<Element | null>
  isOpen: Ref<boolean>
}

const ctx = inject<TooltipCtx>('$tooltip')
const el = ref<HTMLElement | null>(null)

function show() {
  if (ctx) {
    ctx.referenceEl.value = el.value
    ctx.isOpen.value = true
  }
}

function hide() {
  if (ctx) ctx.isOpen.value = false
}
</script>

<template>
  <span
    ref="el"
    data-slot="tooltip-trigger"
    class="inline-flex"
    @mouseenter="show"
    @mouseleave="hide"
    @focusin="show"
    @focusout="hide"
  >
    <slot />
  </span>
</template>
