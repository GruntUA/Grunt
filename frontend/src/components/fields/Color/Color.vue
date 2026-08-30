<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { X } from '@lucide/vue'
import type { BaseFieldProps } from '@/types'
import { Input } from '@/components/ui/input'

const props = defineProps<BaseFieldProps>()
const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const { t } = useI18n()

// Local editable text; the model is only updated once it parses to a full hex.
const text = ref(String(props.modelValue ?? ''))
watch(() => props.modelValue, (v) => { text.value = String(v ?? '') })

const HEX6 = /^#[0-9a-f]{6}$/i

const readonly = computed(() => !!props.disabled || !!props.field.read_only)
const hasValue = computed(() => HEX6.test(text.value))
const invalid = computed(() => !!props.error || (!!text.value && !hasValue.value))
const clearable = computed(() => !readonly.value && !props.field.required && !!text.value)

// The native swatch always needs a concrete colour.
const swatch = computed(() => (hasValue.value ? text.value.toLowerCase() : '#000000'))

function commit(v: string | null) {
  text.value = v ?? ''
  emit('update:modelValue', v)
}

function normalize(raw: string): string {
  let s = raw.trim().replace(/\s+/g, '')
  if (s && !s.startsWith('#')) s = `#${s}`
  // #rgb → #rrggbb
  const short = /^#([0-9a-f])([0-9a-f])([0-9a-f])$/i.exec(s)
  if (short) s = `#${short[1]}${short[1]}${short[2]}${short[2]}${short[3]}${short[3]}`
  return s
}

function onHexInput(raw: string) {
  const s = normalize(raw)
  text.value = s
  if (HEX6.test(s)) emit('update:modelValue', s.toLowerCase())
  else if (!s) emit('update:modelValue', null)
}
</script>

<template>
  <div class="flex items-center gap-2">
    <input
      type="color"
      :value="swatch"
      :disabled="readonly"
      :aria-label="t('Pick a colour')"
      class="size-9 shrink-0 cursor-pointer rounded-md border border-input p-1 disabled:cursor-not-allowed disabled:opacity-60"
      @input="commit(($event.target as HTMLInputElement).value)"
    />
    <Input
      :model-value="text"
      :placeholder="field.placeholder ?? '#000000'"
      :disabled="readonly"
      :maxlength="7"
      :aria-invalid="invalid ? true : undefined"
      :aria-label="field.label"
      class="flex-1 font-mono uppercase"
      @update:model-value="onHexInput(String($event))"
    />
    <button
      v-if="clearable"
      type="button"
      class="shrink-0 rounded-sm p-1 text-muted-foreground transition-colors hover:text-foreground"
      :aria-label="t('Clear')"
      @click="commit(null)"
    >
      <X class="size-4" />
    </button>
  </div>
</template>
