<script setup lang="ts">
import { computed, ref } from 'vue'
import { ComboboxInput } from 'reka-ui'
import type { BaseFieldProps } from '@/types'
import { Input } from '@/components/ui/input'
import { Combobox, ComboboxAnchor, ComboboxItem, ComboboxList, ComboboxViewport } from '@/components/ui/combobox'

const props = defineProps<BaseFieldProps>()
const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const value = computed(() => String(props.modelValue ?? ''))

// A named `validator` (email / phone / url) also drives input semantics: the
// right on-screen keyboard on mobile, sensible browser autofill, and a
// clickable value when the field is permanently read-only.
const SEMANTICS: Record<
  string,
  { type: string; inputmode: string; autocomplete: string; href: (v: string) => string; blank?: boolean }
> = {
  email: { type: 'email', inputmode: 'email', autocomplete: 'email', href: (v) => `mailto:${v}` },
  phone: { type: 'tel', inputmode: 'tel', autocomplete: 'tel', href: (v) => `tel:${v.replace(/[^\d+]/g, '')}` },
  url: {
    type: 'url',
    inputmode: 'url',
    autocomplete: 'url',
    href: (v) => (/^https?:\/\//i.test(v) ? v : `https://${v}`),
    blank: true,
  },
}

const semantics = computed(() => (props.field.validator ? SEMANTICS[props.field.validator] : undefined))

// Render a read-only linkable value as an anchor rather than a dead input.
const asLink = computed(() => !!props.field.read_only && !!semantics.value && !!value.value)

// `options` on a Data field = autocomplete suggestions (one per line). Unlike
// Select the list is open: any text is still a valid value.
const suggestions = computed(() =>
  (props.field.options ?? '').split('\n').map((s) => s.trim()).filter(Boolean),
)
const editable = computed(() => !props.disabled && !props.field.read_only)
const matches = computed(() => {
  const q = value.value.trim().toLowerCase()
  if (!q) return suggestions.value
  return suggestions.value.filter((s) => s.toLowerCase().includes(q) && s.toLowerCase() !== q)
})
const open = ref(false)

const inputProps = computed(() => ({
  modelValue: value.value,
  type: semantics.value?.type ?? 'text',
  inputmode: semantics.value?.inputmode,
  autocomplete: semantics.value?.autocomplete,
  placeholder: props.field.placeholder,
  required: props.field.required,
  disabled: props.disabled || props.field.read_only,
  maxlength: props.field.max_length || undefined,
  'aria-invalid': props.error ? true : undefined,
  class: props.field.bold && 'font-medium',
}))

function onUpdate(v: string | number) {
  emit('update:modelValue', String(v ?? ''))
}

// Trim stray leading/trailing whitespace on commit - a common cause of failed
// unique checks and lookups.
function onBlur(e: FocusEvent) {
  const raw = (e.target as HTMLInputElement).value
  if (raw.trim() !== raw) emit('update:modelValue', raw.trim())
}
</script>

<template>
  <a
    v-if="asLink"
    :href="semantics!.href(value)"
    :target="semantics!.blank ? '_blank' : undefined"
    :rel="semantics!.blank ? 'noopener noreferrer' : undefined"
    class="inline-flex h-9 items-center break-all text-sm text-primary underline-offset-4 hover:underline"
  >
    {{ value }}
  </a>

  <Combobox
    v-else-if="editable && suggestions.length"
    :model-value="value"
    :open="open && matches.length > 0"
    ignore-filter
    open-on-click
    open-on-focus
    :reset-search-term-on-blur="false"
    @update:open="open = $event"
    @update:model-value="(v) => onUpdate(String(v ?? ''))"
  >
    <ComboboxAnchor class="w-full">
      <ComboboxInput as-child :model-value="value">
        <Input v-bind="inputProps" @update:model-value="onUpdate" @blur="onBlur" />
      </ComboboxInput>
    </ComboboxAnchor>
    <ComboboxList align="start" class="w-(--reka-combobox-trigger-width) min-w-56">
      <ComboboxViewport class="max-h-64 p-1">
        <ComboboxItem v-for="s in matches" :key="s" :value="s">
          <span class="truncate">{{ s }}</span>
        </ComboboxItem>
      </ComboboxViewport>
    </ComboboxList>
  </Combobox>

  <Input v-else v-bind="inputProps" @update:model-value="onUpdate" @blur="onBlur" />
</template>
