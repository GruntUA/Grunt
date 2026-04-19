<script setup lang="ts">
import { inject, ref, onMounted } from 'vue'

defineProps<{ asChild?: boolean }>()

const ctx = inject<any>('$dropdown')
const triggerRef = ref<HTMLElement>()

onMounted(() => {
  if (ctx && triggerRef.value) ctx.triggerEl.value = triggerRef.value
})
</script>

<template>
  <span
    ref="triggerRef"
    data-slot="dropdown-menu-trigger"
    style="display: contents"
    @click="ctx?.toggle()"
  >
    <slot />
  </span>
</template>
