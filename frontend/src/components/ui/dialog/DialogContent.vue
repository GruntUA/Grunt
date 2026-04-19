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
  header?: string
}>()

const ctx = inject<any>('$dialog')

const visible = computed({
  get: () => ctx?.isOpen.value ?? false,
  set: (v: boolean) => {
    if (ctx) ctx.isOpen.value = v
  },
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
      root: { class: cn('border-none bg-transparent shadow-none', props.class) },
      mask: { class: 'backdrop-blur-sm bg-background/20' },
      content: { class: 'p-0 bg-transparent' },
    }"
    data-slot="dialog-content"
    v-bind="$attrs"
  >
    <div
      :class="cn(
        'relative flex flex-col w-full bg-card border shadow-2xl rounded-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-200',
        props.contentClass
      )"
    >
      <!-- Optional built-in header if header prop passed -->
      <div v-if="header" class="px-6 py-4 border-b flex items-center justify-between bg-muted/20">
        <h3 class="font-bold text-lg leading-none">{{ header }}</h3>
      </div>

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

    <!-- Pass through PrimeVue slots if used directly -->
    <template v-if="$slots.header" #header>
      <slot name="header" />
    </template>
    <template v-if="$slots.footer" #footer>
      <slot name="footer" />
    </template>
  </PrimeDialog>
</template>

<style scoped>
:deep(.p-dialog-mask) {
  z-index: 50 !important;
}
</style>
