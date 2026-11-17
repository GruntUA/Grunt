<script setup lang="ts">
/**
 * A permission rule's row condition (`DocPermission.match`) as field /
 * operator / value instead of text. The fields come from the DocType being
 * edited (the document holding the rules table, PARENT_DOC); a Link field
 * offers one hop into its target's fields. Text the builder can't show (or a
 * preference for typing) - "as text".
 */
import { computed, inject, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Code, X } from '@lucide/vue'
import type { BaseFieldProps, DocField } from '@/types'
import { metaApi } from '@/core/api/meta'
import { PARENT_DOC } from '@/components/fields/Table/parentDoc'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { formatCondition, parseCondition, type RowCondition } from './condition'

const props = defineProps<BaseFieldProps>()
const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()
const { t } = useI18n()

const parentDoc = inject(PARENT_DOC, undefined)
const text = computed(() => String(props.modelValue ?? ''))
const readonly = computed(() => !!props.disabled || !!props.field.read_only)

// Fields a condition can compare: values, not layout or tables.
const SKIP = new Set(['Section', 'Column', 'Tab', 'HTML', 'HTMLView', 'Button', 'Table', 'MultiLink', 'Image', 'Signature'])
const STANDARD: Pick<DocField, 'fieldname' | 'label' | 'fieldtype' | 'options'>[] = [
  { fieldname: 'owner', label: 'Created by', fieldtype: 'Data' },
  { fieldname: 'modified_by', label: 'Modified by', fieldtype: 'Data' },
  { fieldname: 'name', label: 'ID', fieldtype: 'Data' },
]

type Choice = Pick<DocField, 'fieldname' | 'label' | 'fieldtype' | 'options'>

function choices(fields: unknown): Choice[] {
  const own = (Array.isArray(fields) ? fields : []) as Choice[]
  const usable = own.filter((f) => f.fieldname && !SKIP.has(f.fieldtype))
  const names = new Set(usable.map((f) => f.fieldname))
  return [...usable, ...STANDARD.filter((f) => !names.has(f.fieldname))]
}

const fields = computed(() => choices(parentDoc?.value?.fields))

const parsed = computed(() => parseCondition(text.value))
// Text mode: asked for, or text the builder can't show.
const asText = ref(!!text.value && !parsed.value)
watch(text, (v) => { if (v && !parseCondition(v)) asText.value = true })

const cond = computed<RowCondition>(
  () => parsed.value ?? { field: '', sub: '', op: '==', kind: 'user', value: '' },
)

// A value the grammar can't hold (both quote kinds) - shown, never emitted altered.
const valueError = ref('')
const draftValue = ref<string | null>(null)

function update(patch: Partial<RowCondition>) {
  const next = { ...cond.value, ...patch }
  const formatted = formatCondition(next)
  if (formatted === null) {
    draftValue.value = next.value
    valueError.value = t('A value cannot contain both kinds of quotes')
    return
  }
  draftValue.value = null
  valueError.value = ''
  emit('update:modelValue', formatted || null)
}

// One Link hop: the target's fields, loaded once per DocType.
const targetCache = new Map<string, Choice[]>()
const targetFields = ref<Choice[]>([])
const linkTarget = computed(() => {
  const f = fields.value.find((x) => x.fieldname === cond.value.field)
  return f?.fieldtype === 'Link' && f.options ? String(f.options) : ''
})
watch(
  linkTarget,
  async (target, _old, onCleanup) => {
    // A newer selection makes this one's answer stale.
    let stale = false
    onCleanup(() => { stale = true })
    targetFields.value = []
    if (!target) return
    if (!targetCache.has(target)) {
      let loaded: Choice[]
      try {
        loaded = choices((await metaApi.get(target)).fields)
      } catch {
        loaded = []
      }
      targetCache.set(target, loaded)
    }
    if (!stale) targetFields.value = targetCache.get(target) ?? []
  },
  { immediate: true },
)

function label(f: Choice): string {
  return `${t(f.label || f.fieldname)} (${f.fieldname})`
}
</script>

<template>
  <div class="flex flex-col gap-2">
    <!-- As text -->
    <div v-if="asText" class="flex items-center gap-2">
      <Input
        :model-value="text"
        :disabled="readonly"
        class="font-mono text-xs"
        placeholder="owner == user"
        @update:model-value="emit('update:modelValue', String($event).trim() || null)"
      />
      <Button
        v-if="!readonly && (!text || parsed)"
        variant="ghost"
        size="sm"
        @click="asText = false"
      >
        {{ t('Builder') }}
      </Button>
    </div>

    <!-- Builder -->
    <template v-else>
      <div class="flex flex-wrap items-center gap-2">
        <NativeSelect
          :model-value="cond.field"
          :disabled="readonly"
          class="min-w-48"
          :aria-label="t('Field')"
          @update:model-value="update({ field: String($event), sub: '' })"
        >
          <NativeSelectOption value="">{{ t('All rows') }}</NativeSelectOption>
          <NativeSelectOption v-for="f in fields" :key="f.fieldname" :value="f.fieldname">
            {{ label(f) }}
          </NativeSelectOption>
        </NativeSelect>

        <NativeSelect
          v-if="cond.field && linkTarget"
          :model-value="cond.sub"
          :disabled="readonly"
          class="min-w-40"
          :aria-label="t('Field of the linked document')"
          @update:model-value="update({ sub: String($event) })"
        >
          <NativeSelectOption value="">{{ t('the document itself') }}</NativeSelectOption>
          <NativeSelectOption v-for="f in targetFields" :key="f.fieldname" :value="f.fieldname">
            {{ label(f) }}
          </NativeSelectOption>
        </NativeSelect>

        <template v-if="cond.field">
          <NativeSelect
            :model-value="cond.op"
            :disabled="readonly"
            class="w-auto"
            :aria-label="t('Operator')"
            @update:model-value="update({ op: $event === '!=' ? '!=' : '==' })"
          >
            <NativeSelectOption value="==">{{ t('equals') }}</NativeSelectOption>
            <NativeSelectOption value="!=">{{ t('does not equal') }}</NativeSelectOption>
          </NativeSelect>

          <ToggleGroup
            :model-value="cond.kind"
            type="single"
            variant="outline"
            size="sm"
            :disabled="readonly"
            @update:model-value="(v) => { if (v) update({ kind: v as 'user' | 'value' }) }"
          >
            <ToggleGroupItem value="user">{{ t('Current user') }}</ToggleGroupItem>
            <ToggleGroupItem value="value">{{ t('Value') }}</ToggleGroupItem>
          </ToggleGroup>

          <Input
            v-if="cond.kind === 'value'"
            :model-value="draftValue ?? cond.value"
            :aria-invalid="valueError ? true : undefined"
            :disabled="readonly"
            class="w-48"
            :aria-label="t('Value')"
            @update:model-value="update({ value: String($event) })"
          />

          <Button
            v-if="!readonly"
            variant="ghost"
            size="icon-sm"
            :aria-label="t('Clear')"
            @click="emit('update:modelValue', null)"
          >
            <X />
          </Button>
        </template>

        <Button v-if="!readonly" variant="ghost" size="sm" class="ml-auto" @click="asText = true">
          <Code />
          {{ t('As text') }}
        </Button>
      </div>
      <p v-if="valueError" class="text-xs text-destructive">{{ valueError }}</p>
      <p v-if="text" class="font-mono text-xs text-muted-foreground">{{ text }}</p>
    </template>
  </div>
</template>
