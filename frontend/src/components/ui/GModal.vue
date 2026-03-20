<script setup lang="ts">
import { watch, onMounted, onUnmounted } from 'vue'

const props = withDefaults(defineProps<{
  modelValue: boolean
  title?: string
  size?: 'sm' | 'md' | 'lg'
}>(), { size: 'md' })

const emit = defineEmits<{
  'update:modelValue': [v: boolean]
  confirm: []
}>()

const close = () => emit('update:modelValue', false)

const sizeClass = { sm: 'max-w-sm', md: 'max-w-lg', lg: 'max-w-2xl' }

const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close() }
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))

watch(() => props.modelValue, v => {
  document.body.style.overflow = v ? 'hidden' : ''
})
</script>

<template>
  <Teleport to="body">
    <Transition
      enter-active-class="transition ease-out duration-200"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition ease-in duration-150"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div v-if="modelValue" class="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
        <div class="fixed inset-0 bg-black/40 backdrop-blur-sm" @click="close" />
        <Transition
          enter-active-class="transition ease-out duration-200"
          enter-from-class="opacity-0 scale-95 translate-y-2"
          enter-to-class="opacity-100 scale-100 translate-y-0"
          leave-active-class="transition ease-in duration-150"
          leave-from-class="opacity-100 scale-100 translate-y-0"
          leave-to-class="opacity-0 scale-95 translate-y-2"
        >
          <div v-if="modelValue" :class="['relative bg-[--grunt-surface] rounded-[--grunt-radius-lg] shadow-[--grunt-shadow-md] w-full', sizeClass[size]]">
            <div v-if="title" class="flex items-center justify-between px-6 py-4 border-b border-[--grunt-border]">
              <h3 class="text-base font-semibold text-[--grunt-text-primary]">{{ title }}</h3>
              <button class="text-[--grunt-text-muted] hover:text-[--grunt-text-primary] transition-colors" @click="close">✕</button>
            </div>
            <div class="px-6 py-4"><slot /></div>
            <div v-if="$slots.footer" class="px-6 py-4 border-t border-[--grunt-border] flex justify-end gap-2">
              <slot name="footer" />
            </div>
          </div>
        </Transition>
      </div>
    </Transition>
  </Teleport>
</template>
