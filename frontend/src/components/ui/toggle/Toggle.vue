<script setup lang="ts">
import type { HTMLAttributes } from "vue"
import type { ToggleVariants } from "."
import { cn } from "@/lib/utils"
import { toggleVariants } from "."

const props = withDefaults(defineProps<{
  pressed?: boolean
  disabled?: boolean
  variant?: ToggleVariants["variant"]
  size?: ToggleVariants["size"]
  class?: HTMLAttributes["class"]
}>(), {
  variant: 'default',
  size: 'default',
})

const emit = defineEmits<{
  'update:pressed': [value: boolean]
}>()
</script>

<template>
  <button
    type="button"
    data-slot="toggle"
    :disabled="disabled"
    :data-state="pressed ? 'on' : 'off'"
    :aria-pressed="pressed"
    :class="cn(toggleVariants({ variant, size }), props.class)"
    @click="emit('update:pressed', !pressed)"
  >
    <slot />
  </button>
</template>
