<script setup lang="ts">
import { inject, computed } from 'vue'
import PrimeDrawer from 'primevue/drawer'

const props = defineProps<{
  class?: string
  side?: 'top' | 'right' | 'bottom' | 'left'
}>()

const ctx = inject<any>('$sheet')

const visible = computed({
  get: () => ctx?.isOpen.value ?? false,
  set: (v: boolean) => { if (ctx) ctx.isOpen.value = v },
})

const position = computed(() => props.side ?? 'right')
</script>

<template>
  <PrimeDrawer
    v-model:visible="visible"
    :modal="ctx?.modal?.value ?? true"
    :position="position"
    :show-close-icon="false"
    :pt="{
      root: { class: props.class },
      content: { class: 'p-0 flex flex-col' },
    }"
    data-slot="sheet-content"
  >
    <slot />
  </PrimeDrawer>
</template>
