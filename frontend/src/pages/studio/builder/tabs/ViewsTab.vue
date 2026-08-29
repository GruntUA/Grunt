<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, ref, watch } from 'vue'
import { getRegisteredViewSettings } from '@/core/viewRegistry'
import type { DocType } from '@/types'
import { useBuilderStore } from '@/stores/builder'

const props = defineProps<{
  doctype?: DocType
  modelValue?: Record<string, any>
}>()

const emit = defineEmits<{
  'update:modelValue': [value: Record<string, any>]
}>()

const builder = useBuilderStore()
const isInitializing = ref(true)

watch(
  () => props.modelValue,
  (newVal) => {
    if (!newVal || builder.isSaving || isInitializing.value) return
    builder.doctype = newVal as DocType
  },
  { deep: true },
)

watch(
  () => builder.doctype,
  (newVal) => {
    if (!newVal || isInitializing.value || !props.modelValue) return
    emit('update:modelValue', { ...newVal })
  },
  { deep: true },
)

onMounted(() => {
  if (props.modelValue) {
    builder.doctype = { ...props.modelValue } as DocType
  }
  isInitializing.value = false
})

const registeredSettingsViews = computed(() =>
  getRegisteredViewSettings().map((view) => ({
    type: view.type,
    component: defineAsyncComponent(view.settingsComponent!),
  })),
)
</script>

<template>
  <div class="w-full p-6 space-y-6 overflow-y-auto h-full pb-24">
    <div class="rounded-lg border border-border bg-muted/20 p-4 text-muted-foreground">
      Налаштуйте відображення DocType: список, форму, статуси та розширені уявлення.
    </div>

    <component
      :is="view.component"
      v-for="view in registeredSettingsViews"
      :key="view.type"
    />
  </div>
</template>
