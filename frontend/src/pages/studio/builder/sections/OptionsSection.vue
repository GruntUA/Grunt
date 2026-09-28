<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import { Textarea } from '@/components/ui/textarea'
import HTMLEditor from '@/components/fields/HTMLEditor/HTMLEditor.vue'

const { field, updateField } = usePropertyEditor()
const { t } = useI18n()
</script>

<template>
  <Separator class="!mb-3" />
  <p class="font-semibold text-muted-foreground uppercase tracking-wide mb-3">Options</p>
  <div v-if="field.fieldtype === 'Currency'" class="mb-4 flex flex-col gap-1.5">
    <Input
      :model-value="field.options ?? ''"
      :placeholder="t('currency or UAH')"
      @update:model-value="(v: string | number) => updateField('options', String(v))"
    />
    <p class="text-muted-foreground">{{ t('A Link field to Currency in this document, or a fixed ISO currency code') }}</p>
  </div>
  <div v-else-if="field.fieldtype === 'HTML'" class="mb-4">
    <HTMLEditor
      :field="field"
      :model-value="field.options ?? ''"
      @update:model-value="(v: string) => updateField('options', v)"
    />
  </div>
  <div v-else class="mb-4">
    <Textarea
      :model-value="field.options ?? ''"
      rows="5"
      :placeholder="field.fieldtype === 'Data' ? t('Autocomplete suggestions — one per line') : t('One option per line')"
      class="w-full !text-sm"
      @update:model-value="(v: string | number) => updateField('options', String(v))"
    />
    <div v-if="field.fieldtype === 'Select' || field.fieldtype === 'MultiSelect'" class="mt-3 flex flex-col gap-1">
      <div class="flex items-center gap-2">
        <Checkbox
          id="field-translatable"
          :model-value="!!field.translatable"
          @update:model-value="updateField('translatable', $event)"
        />
        <label for="field-translatable" class="font-medium">{{ t('Translatable') }}</label>
      </div>
      <p class="text-muted-foreground">{{ t('Option captions are translated; stored values stay unchanged.') }}</p>
    </div>
  </div>
</template>
