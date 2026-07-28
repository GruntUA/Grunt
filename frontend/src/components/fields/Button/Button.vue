<script setup lang="ts">
import { shallowRef, watchEffect } from 'vue'
import type { Component } from 'vue'
import type { DocField } from '@/types'
import { Button as ShadcnButton } from '@/components/ui/button'

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

function onClick() {
  emit('update:modelValue', Date.now())
}
</script>

<template>
  <div class="py-1">
    <ShadcnButton :variant="field.options as any" type="button" :disabled="disabled || field.read_only" class="w-full sm:w-auto gap-2" @click="onClick">
      <component :is="iconComponent" v-if="iconComponent" class="size-4 shrink-0" />
      {{ field.label }}
    </ShadcnButton>
  </div>
</template>
