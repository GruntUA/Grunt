<script setup lang="ts">
import { shallowRef, watchEffect } from 'vue'
import type { Component } from 'vue'
import type { DocField } from '@/types'
import Button from 'primevue/button'

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const iconComponent = shallowRef<Component | null>(null)

watchEffect(async () => {
  const name = props.field.icon
  if (!name) { iconComponent.value = null; return }
  const pascal = name.split('-').map((s: string) => s.charAt(0).toUpperCase() + s.slice(1)).join('')
  const lib = await import('@lucide/vue') as unknown as Record<string, Component>
  iconComponent.value = lib[pascal] ?? null
})

const severity = (): string | undefined => {
  const v = props.field.options
  if (v === 'secondary') return 'secondary'
  if (v === 'destructive') return 'danger'
  return undefined
}

const variant = (): "outlined" | "text" | "link" | undefined => {
  const v = props.field.options
  if (v === 'outline') return 'outlined'
  if (v === 'ghost') return 'text'
  return undefined
}

function onClick() {
  emit('update:modelValue', Date.now())
}
</script>

<template>
  <div class="py-1">
    <Button
      type="button"
      :severity="severity()"
      :variant="variant()"
      :disabled="disabled || field.read_only"
      class="w-full sm:w-auto gap-2"
      @click="onClick"
    >
      <component :is="iconComponent" v-if="iconComponent" class="size-4 shrink-0" />
      {{ field.label }}
    </Button>
  </div>
</template>
