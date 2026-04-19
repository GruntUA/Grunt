<script setup lang="ts">
import { inject, computed } from 'vue'
import PrimeDialog from 'primevue/dialog'
import { X } from '@lucide/vue'
import { cn } from '@/lib/utils'

const props = defineProps<{
  class?: string
  contentClass?: string
  hideClose?: boolean
  width?: string | number
}>()

const ctx = inject<any>('$dialog')

const visible = computed({
  get: () => ctx?.isOpen.value ?? false,
  set: (v: boolean) => { if (ctx) ctx.isOpen.value = v },
})

const widthStyle = computed(() => {
  if (!props.width) return undefined
  return typeof props.width === 'number' ? `${props.width}px` : props.width
})
</script>

<template>
  <PrimeDialog
    v-model:visible="visible"
    :modal="ctx?.modal?.value ?? true"
    :closable="false"
    :show-header="false"
    :style="{ width: widthStyle }"
    :pt="{
      root: { class: cn('border-none bg-transparent shadow-none max-h-[90vh]', props.class) },
      mask: { class: 'backdrop-blur-sm bg-background/20' },
      content: { class: 'p-0 bg-transparent flex flex-col overflow-hidden px-4 py-8' },
    }"
    data-slot="dialog-scroll-content"
    v-bind="$attrs"
  >
    <div
      :class="cn(
        'relative flex flex-col w-full bg-card border shadow-2xl rounded-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-200',
        props.contentClass
      )"
    >
      <div class="flex-1 overflow-y-auto">
        <slot />
      </div>

      <button
        v-if="!hideClose"
        class="absolute top-4 right-4 z-50 p-1.5 rounded-full bg-muted/50 text-muted-foreground hover:bg-muted hover:text-foreground transition-all focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
        @click="ctx?.close()"
      >
        <X class="size-4" />
        <span class="sr-only">Close</span>
      </button>
    </div>
  </PrimeDialog>
</template>
