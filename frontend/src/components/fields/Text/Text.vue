<script setup lang="ts">
import { computed } from 'vue'
import type { BaseFieldProps } from '@/types'
import { Input } from '@/components/ui/input'

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

function onUpdate(v: string | number) {
  emit('update:modelValue', String(v ?? ''))
}

// Trim stray leading/trailing whitespace on commit — a common cause of failed
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

  <Input
    v-else
    :model-value="value"
    :type="semantics?.type ?? 'text'"
    :inputmode="semantics?.inputmode"
    :autocomplete="semantics?.autocomplete"
    :placeholder="field.placeholder"
    :required="field.required"
    :disabled="disabled || field.read_only"
    :maxlength="field.max_length || undefined"
    :aria-invalid="error ? true : undefined"
    :class="field.bold && 'font-medium'"
    @update:model-value="onUpdate"
    @blur="onBlur"
  />
</template>
