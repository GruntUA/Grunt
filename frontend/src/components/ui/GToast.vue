<script setup lang="ts">
import { useToast } from '@/core/composables/useToast'

const { toasts, remove } = useToast()

const iconPath = {
  success: 'M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
  error:   'M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z',
  info:    'M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z',
}
const iconColor = { success: 'text-[--grunt-primary]', error: 'text-[--grunt-danger]', info: 'text-blue-500' }
</script>

<template>
  <div class="fixed bottom-5 right-5 z-[100] flex flex-col gap-2 w-80">
    <TransitionGroup
      enter-active-class="transition ease-out duration-300"
      enter-from-class="opacity-0 translate-x-8"
      enter-to-class="opacity-100 translate-x-0"
      leave-active-class="transition ease-in duration-200"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0 translate-x-8"
    >
      <div
        v-for="t in toasts"
        :key="t.id"
        class="flex items-start gap-3 bg-[--grunt-surface] border border-[--grunt-border] rounded-[--grunt-radius-md] shadow-[--grunt-shadow-md] px-4 py-3"
      >
        <svg :class="['h-5 w-5 mt-0.5 flex-shrink-0', iconColor[t.type]]" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" :d="iconPath[t.type]" />
        </svg>
        <p class="flex-1 text-sm text-[--grunt-text-primary]">{{ t.message }}</p>
        <button class="text-[--grunt-text-muted] hover:text-[--grunt-text-primary] text-xs" @click="remove(t.id)">✕</button>
      </div>
    </TransitionGroup>
  </div>
</template>
