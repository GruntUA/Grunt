<template>
  <Teleport to="body">
    <Transition
      enter-active-class="ease-out duration-300"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="ease-in duration-200"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div v-if="show" class="relative z-50" aria-labelledby="modal-title" role="dialog" aria-modal="true">
        <!-- Backdrop -->
        <div class="fixed inset-0 bg-gray-500 bg-opacity-75 backdrop-blur-sm transition-opacity" @click="$emit('close')"></div>

        <div class="fixed inset-0 z-10 w-screen overflow-y-auto">
          <div class="flex min-h-full items-end justify-center p-4 text-center sm:items-center sm:p-0">
            <Transition
              enter-active-class="ease-out duration-300"
              enter-from-class="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95"
              enter-to-class="opacity-100 translate-y-0 sm:scale-100"
              leave-active-class="ease-in duration-200"
              leave-from-class="opacity-100 translate-y-0 sm:scale-100"
              leave-to-class="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95"
            >
              <div v-if="show" class="relative transform overflow-hidden rounded-lg bg-white text-left shadow-xl transition-all sm:my-8 sm:w-full sm:max-w-lg">
                <!-- Close Button -->
                <div class="absolute right-0 top-0 hidden pr-4 pt-4 sm:block">
                  <button type="button" class="rounded-md bg-white text-gray-400 hover:text-gray-500 focus-ring" @click="$emit('close')">
                    <span class="sr-only">Close</span>
                    <svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
                
                <!-- Content -->
                <div class="bg-white px-4 pb-4 pt-5 sm:p-6 sm:pb-4">
                  <slot></slot>
                </div>

                <!-- Footer -->
                <div v-if="$slots.footer" class="bg-gray-50 px-4 py-3 sm:flex sm:flex-row-reverse sm:px-6">
                  <slot name="footer"></slot>
                </div>
              </div>
            </Transition>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { watch } from 'vue'

const props = defineProps<{
  show: boolean
}>()

const emit = defineEmits(['close'])

// Prevent body scrolling when modal is open
watch(() => props.show, (val) => {
  if (val) {
    document.body.style.overflow = 'hidden'
  } else {
    document.body.style.overflow = ''
  }
})
</script>
