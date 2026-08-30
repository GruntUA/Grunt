<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { BaseFieldProps } from '@/types'
import { Input } from '@/components/ui/input'
import { Eye, EyeOff } from '@lucide/vue'

defineProps<BaseFieldProps>()
const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const { t } = useI18n()
const revealed = ref(false)
const capsLock = ref(false)

function onKey(e: KeyboardEvent) {
  capsLock.value = e.getModifierState?.('CapsLock') ?? false
}
</script>

<template>
  <div class="relative">
    <Input
      :model-value="String(modelValue ?? '')"
      :type="revealed ? 'text' : 'password'"
      :placeholder="field.placeholder ?? undefined"
      :required="field.required"
      :disabled="disabled || field.read_only"
      :aria-invalid="error ? true : undefined"
      :aria-label="field.label"
      autocomplete="new-password"
      class="w-full pr-9"
      @update:model-value="emit('update:modelValue', $event)"
      @keydown="onKey"
      @keyup="onKey"
      @blur="capsLock = false"
    />
    <button
      type="button"
      class="absolute inset-y-0 right-0 flex items-center px-2.5 text-muted-foreground hover:text-foreground disabled:opacity-50"
      :aria-label="revealed ? t('Hide') : t('Show')"
      :aria-pressed="revealed"
      :disabled="disabled || field.read_only"
      tabindex="-1"
      @click="revealed = !revealed"
    >
      <component :is="revealed ? EyeOff : Eye" class="size-4" />
    </button>
    <p v-if="capsLock" class="mt-1 text-xs text-warning">{{ t('Caps Lock is on') }}</p>
  </div>
</template>
