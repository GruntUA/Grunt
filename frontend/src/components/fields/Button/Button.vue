<script setup lang="ts">
import { computed, shallowRef, watchEffect } from 'vue'
import type { Component } from 'vue'
import type { DocField } from '@/types'
import { Button as ShadcnButton, type ButtonVariants } from '@/components/ui/button'
import { resolveLucideIcon } from '@/lib/lucide'

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const VARIANTS = new Set<NonNullable<ButtonVariants['variant']>>([
  'default', 'destructive', 'outline', 'secondary', 'ghost', 'link',
])

const variant = computed<ButtonVariants['variant']>(() => {
  const o = props.field.options as ButtonVariants['variant']
  return o && VARIANTS.has(o) ? o : 'default'
})

const iconComponent = shallowRef<Component | null>(null)
watchEffect(async () => {
  iconComponent.value = await resolveLucideIcon(props.field.icon)
})

function onClick() {
  emit('update:modelValue', Date.now())
}
</script>

<template>
  <div class="py-1">
    <ShadcnButton
      :variant="variant"
      type="button"
      :disabled="disabled || field.read_only"
      class="w-full gap-2 sm:w-auto"
      @click="onClick"
    >
      <component :is="iconComponent" v-if="iconComponent" class="size-4 shrink-0" />
      {{ field.label }}
    </ShadcnButton>
  </div>
</template>
