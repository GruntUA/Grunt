<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { BaseFieldProps } from '@/types'
import { Input } from '@/components/ui/input'
import { Check, Circle, Eye, EyeOff } from '@lucide/vue'
import client from '@/core/api/client'

const props = defineProps<BaseFieldProps>()
const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const { t } = useI18n()
const revealed = ref(false)
const capsLock = ref(false)

function onKey(e: KeyboardEvent) {
  capsLock.value = e.getModifierState?.('CapsLock') ?? false
}

// ── Password policy checklist (opt-in via field.show_strength) ──────────────
type Policy = {
  min_length: number
  require_uppercase: boolean
  require_lowercase: boolean
  require_numbers: boolean
  require_symbols: boolean
}

// Shared across every Password field on the page — the policy never changes
// within a session, so fetch it once.
let _policy: Promise<Policy> | null = null
function loadPolicy(): Promise<Policy> {
  if (!_policy) {
    _policy = client
      .get('/api/v1/method/grunt.auth.password_policy.password_policy_api')
      .then((r) => r.data?.data as Policy)
      .catch((err) => { _policy = null; throw err })
  }
  return _policy
}

const policy = ref<Policy | null>(null)
onMounted(() => {
  if (props.field.show_strength) loadPolicy().then((p) => { policy.value = p }).catch(() => {})
})

const checks = computed(() => {
  const p = policy.value
  if (!p) return []
  const v = String(props.modelValue ?? '')
  const rules: { key: string; label: string; ok: boolean }[] = [
    { key: 'len', label: t('At least {min} characters').replace('{min}', String(p.min_length)), ok: v.length >= p.min_length },
  ]
  if (p.require_uppercase) rules.push({ key: 'upper', label: t('An uppercase letter'), ok: /\p{Lu}/u.test(v) })
  if (p.require_lowercase) rules.push({ key: 'lower', label: t('A lowercase letter'), ok: /\p{Ll}/u.test(v) })
  if (p.require_numbers) rules.push({ key: 'digit', label: t('A digit'), ok: /\d/.test(v) })
  if (p.require_symbols) rules.push({ key: 'symbol', label: t('A special character'), ok: /[^\p{L}\p{N}]/u.test(v) })
  return rules
})
</script>

<template>
  <div>
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
    </div>
    <p v-if="capsLock" class="mt-1 text-warning">{{ t('Caps Lock is on') }}</p>
    <ul v-if="checks.length" class="mt-1.5 space-y-1">
      <li
        v-for="c in checks"
        :key="c.key"
        class="flex items-center gap-1.5"
        :class="c.ok ? 'text-success' : 'text-muted-foreground'"
      >
        <component :is="c.ok ? Check : Circle" class="size-3 shrink-0" />
        <span>{{ c.label }}</span>
      </li>
    </ul>
  </div>
</template>
