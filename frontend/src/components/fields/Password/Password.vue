<script setup lang="ts">
import { ref } from 'vue'
import type { BaseFieldProps } from '@/types'
import { Input } from '@/components/ui/input'
import { Eye, EyeOff } from '@lucide/vue'

defineProps<BaseFieldProps>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const revealed = ref(false)
</script>

<template>
  <div class="relative">
    <Input
      :model-value="String(modelValue ?? '')"
      :type="revealed ? 'text' : 'password'"
      :placeholder="field.placeholder ?? field.label"
      :required="field.required"
      :disabled="disabled || field.read_only"
      autocomplete="off"
      class="w-full pr-9"
      @update:model-value="emit('update:modelValue', $event)"
    />
    <button
      type="button"
      class="absolute inset-y-0 right-0 flex items-center px-2.5 text-muted-foreground hover:text-foreground disabled:opacity-50"
      :aria-label="revealed ? 'Сховати' : 'Показати'"
      :disabled="disabled || field.read_only"
      tabindex="-1"
      @click="revealed = !revealed"
    >
      <component :is="revealed ? EyeOff : Eye" class="size-4" />
    </button>
  </div>
</template>
