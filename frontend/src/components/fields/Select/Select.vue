<script setup lang="ts">
import { computed, shallowRef, watchEffect, type Component } from 'vue'
import { useI18n } from 'vue-i18n'
import { X } from '@lucide/vue'
import type { BaseFieldProps } from '@/types'
import { parseSelectOptions, resolveOptionIcons } from '@/lib/selectOptions'
import {
  Select as ShadcnSelect,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from '@/components/ui/select'

const props = defineProps<BaseFieldProps>()
const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const { t } = useI18n()

const parsedOptions = computed(() => parseSelectOptions(props.field.options))

// Lazily resolve icon names → components, keyed by name.
const iconMap = shallowRef<Record<string, Component>>({})
watchEffect(async () => {
  iconMap.value = await resolveOptionIcons(parsedOptions.value)
})

const resolvedOptions = computed(() =>
  parsedOptions.value.map((o) => ({
    value: o.value,
    icon: o.icon ? (iconMap.value[o.icon] ?? null) : null,
  })),
)

const current = computed(() => {
  const v = props.modelValue
  return v == null || v === '' ? undefined : String(v)
})

const currentOption = computed(
  () => resolvedOptions.value.find((o) => o.value === current.value) ?? null,
)

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
        <span v-if="currentOption" class="flex items-center gap-2">
          <component :is="currentOption.icon" v-if="currentOption.icon" class="size-4 text-muted-foreground" />
          {{ currentOption.value }}
        </span>
        <span v-else class="text-muted-foreground">{{ field.placeholder ?? t('— select —') }}</span>
      </SelectTrigger>
      <SelectContent>
        <SelectItem v-for="opt in resolvedOptions" :key="opt.value" :value="opt.value">
          <component :is="opt.icon" v-if="opt.icon" class="size-4" />
          {{ opt.value }}
        </SelectItem>
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
