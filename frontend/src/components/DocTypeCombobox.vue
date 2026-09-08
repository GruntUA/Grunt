<script setup lang="ts">
import { Check, ChevronsUpDown } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import {
  Combobox,
  ComboboxAnchor,
  ComboboxEmpty,
  ComboboxGroup,
  ComboboxInput,
  ComboboxItem,
  ComboboxItemIndicator,
  ComboboxList,
  ComboboxTrigger,
} from '@/components/ui/combobox'
import { cn } from '@/lib/utils'

const props = withDefaults(
  defineProps<{
    modelValue: string
    options: string[]
    placeholder?: string
    emptyMessage?: string
    disabled?: boolean
    class?: string
  }>(),
  {
    placeholder: '— оберіть —',
    emptyMessage: 'Нічого не знайдено',
  },
)

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
</script>

<template>
  <Combobox
    :model-value="modelValue || undefined"
    :disabled="disabled"
    @update:model-value="(v) => emit('update:modelValue', (v as string | null) ?? '')"
  >
    <ComboboxAnchor as-child>
      <ComboboxTrigger as-child>
        <Button
          variant="outline"
          role="combobox"
          :class="cn('justify-between font-normal', !modelValue && 'text-muted-foreground', props.class)"
        >
          <span class="truncate">{{ modelValue || placeholder }}</span>
          <ChevronsUpDown class="size-4 shrink-0 opacity-50" />
        </Button>
      </ComboboxTrigger>
    </ComboboxAnchor>

    <ComboboxList class="w-(--reka-combobox-trigger-width) min-w-56">
      <ComboboxInput :placeholder="placeholder" />
      <ComboboxEmpty>{{ emptyMessage }}</ComboboxEmpty>
      <ComboboxGroup class="max-h-64 overflow-y-auto">
        <ComboboxItem v-for="opt in options" :key="opt" :value="opt">
          <span class="truncate">{{ opt }}</span>
          <ComboboxItemIndicator class="ml-auto">
            <Check class="size-4" />
          </ComboboxItemIndicator>
        </ComboboxItem>
      </ComboboxGroup>
    </ComboboxList>
  </Combobox>
</template>
