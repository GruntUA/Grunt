<script setup lang="ts">
import { computed } from 'vue'
import { useBuilderStore } from '@/stores/builder'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Checkbox } from '@/components/ui/checkbox'

const builder = useBuilderStore()
const field = computed(() => builder.selectedField)

const LAYOUT_TYPES = new Set(['Tab', 'Section', 'Column'])
const isLayout = computed(() => !!field.value && LAYOUT_TYPES.has(field.value.fieldtype))
const isSection = computed(() => field.value?.fieldtype === 'Section')

function update(patch: Record<string, unknown>) {
  if (!builder.selectedFieldName) return
  builder.updateField(builder.selectedFieldName, patch as never)
}
</script>

<template>
  <div class="h-full overflow-y-auto p-4 border-l border-border bg-card">
    <template v-if="field">
      <p class="font-semibold text-muted-foreground uppercase tracking-wide mb-4">
        {{ isLayout ? field.fieldtype : field.fieldname }}
      </p>

      <div class="flex flex-col gap-1.5 mb-4">
        <label class="font-medium">Підпис</label>
        <Input :model-value="field.label" class="w-full" @update:model-value="update({ label: $event })" />
      </div>

      <div v-if="isSection" class="flex items-center gap-2 mb-4">
        <Checkbox :model-value="!!field.collapsible" @update:model-value="update({ collapsible: !!$event })" />
        <label class="font-medium">Згортається</label>
      </div>

      <template v-if="!isLayout">
        <div class="flex items-center gap-2 mb-3">
          <Checkbox :model-value="!!field.required" @update:model-value="update({ required: !!$event })" />
          <label class="font-medium">Обов'язкове</label>
        </div>
        <div class="flex items-center gap-2 mb-4">
          <Checkbox :model-value="!!field.hidden" @update:model-value="update({ hidden: !!$event })" />
          <label class="font-medium">Приховане на формі</label>
        </div>
        <div class="flex flex-col gap-1.5 mb-4">
          <label class="font-medium">Підказка</label>
          <Textarea :model-value="field.description" class="w-full" @update:model-value="update({ description: $event })" />
        </div>
      </template>
    </template>

    <div v-else class="flex items-center justify-center h-32 text-muted-foreground">
      Оберіть поле для редагування
    </div>
  </div>
</template>
