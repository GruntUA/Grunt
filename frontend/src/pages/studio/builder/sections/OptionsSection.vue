<script setup lang="ts">
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import { Textarea } from '@/components/ui/textarea'
import HTMLEditor from '@/components/fields/HTMLEditor/HTMLEditor.vue'

const { field, updateField } = usePropertyEditor()
</script>

<template>
  <Separator class="!mb-3" />
  <p class="font-semibold text-muted-foreground uppercase tracking-wide mb-3">Options</p>
  <div v-if="field.fieldtype === 'Currency'" class="mb-4 flex flex-col gap-1.5">
    <Input
      :model-value="field.options ?? ''"
      placeholder="currency або UAH"
      @update:model-value="(v: string | number) => updateField('options', String(v))"
    />
    <p class="text-muted-foreground">Поле-посилання на Currency у цьому документі або фіксований ISO-код валюти</p>
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
      :placeholder="field.fieldtype === 'Data' ? 'Підказки автодоповнення — кожна з нового рядка' : 'Кожна опція з нового рядка'"
      class="w-full !text-sm"
      @update:model-value="(v: string | number) => updateField('options', String(v))"
    />
  </div>
</template>
