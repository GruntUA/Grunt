<script setup lang="ts">
// A date filter value: a fixed date (the #absolute slot - the field's own
// picker) or a number of days from today (`today-30`), resolved by the server
// each time the filter is applied.
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { InputGroup, InputGroupAddon, InputGroupInput, InputGroupText } from '@/components/ui/input-group'
import { MAX_RELATIVE_DAYS, parseRelativeDays, relativeDateValue } from '@/core/relativeDate'

const props = defineProps<{ modelValue: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const { t } = useI18n()

const relative = ref(parseRelativeDays(props.modelValue) !== null)
// A value set from outside (a saved filter, a reset) decides the mode; an empty
// one - the days input cleared - keeps it.
watch(() => props.modelValue, (v) => {
  if (v) relative.value = parseRelativeDays(v) !== null
})

const mode = computed({
  get: () => (relative.value ? 'relative' : 'date'),
  set: (m: string) => {
    relative.value = m === 'relative'
    emit('update:modelValue', relative.value ? relativeDateValue(0) : '')
  },
})

const days = computed({
  get: () => parseRelativeDays(props.modelValue) ?? 0,
  set: (v: number | string) => emit('update:modelValue', relativeDateValue(Number(v))),
})
</script>

<template>
  <div class="flex min-w-0 items-center gap-2">
    <Select v-model="mode">
      <SelectTrigger class="w-auto shrink-0" :aria-label="t('Date filter kind')">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="date">{{ t('On date') }}</SelectItem>
        <SelectItem value="relative">{{ t('From today') }}</SelectItem>
      </SelectContent>
    </Select>
    <InputGroup v-if="relative" class="min-w-0 flex-1">
      <InputGroupInput
        v-model="days"
        type="number"
        step="1"
        :min="-MAX_RELATIVE_DAYS"
        :max="MAX_RELATIVE_DAYS"
        inputmode="numeric"
        :aria-label="t('Days from today')"
        :title="t('A negative number - days ago')"
      />
      <InputGroupAddon align="inline-end">
        <InputGroupText>{{ t('days') }}</InputGroupText>
      </InputGroupAddon>
    </InputGroup>
    <div v-else class="min-w-0 flex-1">
      <slot name="absolute" />
    </div>
  </div>
</template>
