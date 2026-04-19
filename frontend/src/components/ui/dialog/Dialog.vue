<script setup lang="ts">
import { ref, computed, provide } from 'vue'

const props = defineProps<{
  open?: boolean
  modal?: boolean
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()

const internalOpen = ref(false)

const isOpen = computed({
  get: () => props.open !== undefined ? props.open : internalOpen.value,
  set: (value: boolean) => {
    internalOpen.value = value
    emit('update:open', value)
  }
})

provide('$dialog', {
  isOpen,
  modal: computed(() => props.modal ?? true),
  open: () => { isOpen.value = true },
  close: () => { isOpen.value = false },
})
</script>

<template>
  <slot />
</template>
