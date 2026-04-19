<script setup lang="ts">
import { inject, onMounted, ref } from 'vue'

defineProps<{ asChild?: boolean }>()

const ctx = inject<{
  toggle: () => void
  setTrigger: (el: HTMLElement) => void
}>('$popover')

const wrapperEl = ref<HTMLElement | null>(null)

onMounted(() => {
  const child = wrapperEl.value?.firstElementChild as HTMLElement | null
  if (child) ctx?.setTrigger(child)
})
</script>

<template>
  <span ref="wrapperEl" style="display: contents" @click="ctx?.toggle()">
    <slot />
  </span>
</template>
