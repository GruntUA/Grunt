<script setup lang="ts">
import { inject, computed } from 'vue'
import PrimeDialog from 'primevue/dialog'
import { X } from '@lucide/vue'

const props = defineProps<{
  class?: string
  hideClose?: boolean
}>()

const ctx = inject<any>('$dialog')

const visible = computed({
  get: () => ctx?.isOpen.value ?? false,
  set: (v: boolean) => { if (ctx) ctx.isOpen.value = v },
})
</script>

<template>
  <PrimeDialog
    v-model:visible="visible"
    :modal="ctx?.modal?.value ?? true"
    :closable="false"
    :show-header="false"
    :pt="{
      root: { class: ['relative', props.class] },
      content: { class: 'p-0 overflow-y-auto' },
    }"
    data-slot="dialog-scroll-content"
  >
    <slot />
    <button
      v-if="!hideClose"
      class="absolute top-4 right-4 z-10 rounded-sm opacity-70 hover:opacity-100 focus:outline-none transition-opacity"
      @click="ctx?.close()"
    >
      <X class="size-4" />
      <span class="sr-only">Close</span>
    </button>
  </PrimeDialog>
</template>
