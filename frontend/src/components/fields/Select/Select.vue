<script setup lang="ts">
import { computed, inject, shallowRef, watchEffect, type Component } from 'vue'
import { useI18n } from 'vue-i18n'
import { X } from '@lucide/vue'
import type { BaseFieldProps } from '@/types'
import { parseSelectOptions, resolveOptionIcons } from '@/lib/selectOptions'
import { STATUS_CONFIG, statusToneClass } from '@/core/status'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Select as ShadcnSelect,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from '@/components/ui/select'

const props = defineProps<BaseFieldProps>()
const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const { t } = useI18n()

const parsedOptions = computed(() => parseSelectOptions(props.field.options, props.field.option_labels))

// Lazily resolve icon names -> components, keyed by name.
const iconMap = shallowRef<Record<string, Component>>({})
watchEffect(async () => {
  iconMap.value = await resolveOptionIcons(parsedOptions.value)
})

// On the status field of the surrounding DocType options render as the same
// coloured badges as in lists.
const statusConfig = inject(STATUS_CONFIG, null)
const indicators = computed(() =>
  statusConfig?.value?.field === props.field.fieldname ? statusConfig.value.indicators : null,
)

const resolvedOptions = computed(() =>
  parsedOptions.value.map((o) => {
    const ind = indicators.value?.find((i) => i.value === o.value)
    return {
      value: o.value,
      label: ind?.label || o.label,
      icon: o.icon ? (iconMap.value[o.icon] ?? null) : null,
      tone: indicators.value ? statusToneClass(ind?.color) : null,
    }
  }),
)

const current = computed(() => {
  const v = props.modelValue
  return v == null || v === '' ? undefined : String(v)
})

const currentOption = computed(
  () => resolvedOptions.value.find((o) => o.value === current.value) ?? null,
)

const readonly = computed(() => !!props.disabled || !!props.field.read_only)

// Optional fields get a clear affordance - reka Select has no native deselect.
const clearable = computed(() => !readonly.value && !props.field.required && current.value != null)
</script>

<template>
  <div v-if="readonly && currentOption?.tone" class="flex min-h-9 items-center">
    <Badge variant="outline" :class="['font-normal', currentOption.tone]">
      <component :is="currentOption.icon" v-if="currentOption.icon" class="size-3.5" />
      {{ currentOption.label }}
    </Badge>
  </div>

  <div v-else class="relative w-full">
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
        <Badge v-if="currentOption?.tone" variant="outline" :class="['font-normal', currentOption.tone]">
          <component :is="currentOption.icon" v-if="currentOption.icon" class="size-3.5" />
          {{ currentOption.label }}
        </Badge>
        <span v-else-if="currentOption" class="flex items-center gap-2">
          <component :is="currentOption.icon" v-if="currentOption.icon" class="size-4 text-muted-foreground" />
          {{ currentOption.label }}
        </span>
        <span v-else class="text-muted-foreground">{{ field.placeholder ?? t('— select —') }}</span>
      </SelectTrigger>
      <SelectContent>
        <SelectItem v-for="opt in resolvedOptions" :key="opt.value" :value="opt.value">
          <Badge v-if="opt.tone" variant="outline" :class="['font-normal', opt.tone]">
            <component :is="opt.icon" v-if="opt.icon" class="size-3.5" />
            {{ opt.label }}
          </Badge>
          <template v-else>
            <component :is="opt.icon" v-if="opt.icon" class="size-4" />
            {{ opt.label }}
          </template>
        </SelectItem>
      </SelectContent>
    </ShadcnSelect>

    <Button
      v-if="clearable"
      type="button"
      variant="ghost"
      size="icon-xs"
      class="absolute top-1/2 right-8 -translate-y-1/2 text-muted-foreground"
      :aria-label="t('Clear')"
      tabindex="-1"
      @pointerdown.stop.prevent="emit('update:modelValue', null)"
    >
      <X />
    </Button>
  </div>
</template>
