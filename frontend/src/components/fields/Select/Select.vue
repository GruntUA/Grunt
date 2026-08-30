<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { X } from '@lucide/vue'
import type { BaseFieldProps } from '@/types'
import {
  Select as ShadcnSelect,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

const props = defineProps<BaseFieldProps>()
const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const { t } = useI18n()

const parsedOptions = computed(() =>
  typeof props.field.options === 'string'
    ? props.field.options.split('\n').map((o) => o.trim()).filter(Boolean)
    : (Array.isArray(props.field.options) ? props.field.options : []),
)

const current = computed(() => {
  const v = props.modelValue
  return v == null || v === '' ? undefined : String(v)
})

const readonly = computed(() => !!props.disabled || !!props.field.read_only)

// Optional fields get a clear affordance — reka Select has no native deselect.
const clearable = computed(() => !readonly.value && !props.field.required && current.value != null)
</script>

<template>
  <div class="relative w-full">
    <ShadcnSelect
      :model-value="current"
      :disabled="readonly"
      @update:model-value="emit('update:modelValue', $event)"
    >
      <SelectTrigger
        class="w-full"
        :class="[clearable && 'pr-14', field.bold && 'font-medium']"
        :aria-invalid="error ? true : undefined"
        :aria-label="field.label"
      >
        <SelectValue :placeholder="field.placeholder ?? t('— select —')" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem v-for="opt in parsedOptions" :key="opt" :value="opt">{{ opt }}</SelectItem>
      </SelectContent>
    </ShadcnSelect>

    <button
      v-if="clearable"
      type="button"
      class="absolute inset-y-0 right-8 flex items-center px-1 text-muted-foreground transition-colors hover:text-foreground"
      :aria-label="t('Clear')"
      tabindex="-1"
      @pointerdown.stop.prevent="emit('update:modelValue', null)"
    >
      <X class="size-4" />
    </button>
  </div>
</template>
