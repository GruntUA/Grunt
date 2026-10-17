<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, useId } from 'vue'
import { useBuilderStore } from '@/stores/builder'
import { getLayoutTypeSet } from '@/core/fieldRegistry'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Checkbox } from '@/components/ui/checkbox'
import { Empty, EmptyDescription } from '@/components/ui/empty'
import { Field, FieldGroup, FieldLabel, FieldLegend, FieldSet } from '@/components/ui/field'

const { t } = useI18n()
const id = useId()

const builder = useBuilderStore()
const field = computed(() => builder.selectedField)

const LAYOUT_TYPES = getLayoutTypeSet()
const isLayout = computed(() => !!field.value && LAYOUT_TYPES.has(field.value.fieldtype))
const isSection = computed(() => field.value?.fieldtype === 'Section')

function update(patch: Record<string, unknown>) {
  if (!builder.selectedFieldName) return
  builder.updateField(builder.selectedFieldName, patch as never)
}
</script>

<template>
  <div class="h-full overflow-y-auto p-4 border-l border-border bg-card">
    <FieldSet v-if="field">
      <FieldLegend variant="label">{{ isLayout ? field.fieldtype : field.fieldname }}</FieldLegend>
      <FieldGroup class="gap-4">
        <Field>
          <FieldLabel :for="`${id}-label`">{{ t('Label') }}</FieldLabel>
          <Input :id="`${id}-label`" :model-value="field.label" @update:model-value="update({ label: $event })" />
        </Field>

        <Field v-if="isSection" orientation="horizontal">
          <Checkbox :id="`${id}-collapsible`" :model-value="!!field.collapsible" @update:model-value="update({ collapsible: !!$event })" />
          <FieldLabel :for="`${id}-collapsible`" class="font-normal">{{ t('Collapsible') }}</FieldLabel>
        </Field>

        <template v-if="!isLayout">
          <Field orientation="horizontal">
            <Checkbox :id="`${id}-required`" :model-value="!!field.required" @update:model-value="update({ required: !!$event })" />
            <FieldLabel :for="`${id}-required`" class="font-normal">{{ t('Required') }}</FieldLabel>
          </Field>
          <Field orientation="horizontal">
            <Checkbox :id="`${id}-hidden`" :model-value="!!field.hidden" @update:model-value="update({ hidden: !!$event })" />
            <FieldLabel :for="`${id}-hidden`" class="font-normal">{{ t('Hidden on the form') }}</FieldLabel>
          </Field>
          <Field>
            <FieldLabel :for="`${id}-description`">{{ t('Help text') }}</FieldLabel>
            <Textarea :id="`${id}-description`" :model-value="field.description" @update:model-value="update({ description: $event })" />
          </Field>
        </template>
      </FieldGroup>
    </FieldSet>

    <Empty v-else>
      <EmptyDescription>{{ t('Select a field to edit') }}</EmptyDescription>
    </Empty>
  </div>
</template>
