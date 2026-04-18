<script setup lang="ts">
import type { WorkflowState } from '@/types'
import { Input } from '@/components/ui/input'
import { Field, FieldLabel } from '@/components/ui/field'
import { Button } from '@/components/ui/button'

const props = defineProps<{ state: WorkflowState }>()
const emit = defineEmits<{
  update: [state: WorkflowState]
  remove: []
}>()

function update(key: keyof WorkflowState, val: unknown) {
  emit('update', { ...props.state, [key]: val })
}
</script>

<template>
  <div class="p-4 border-l border-border bg-background w-64 flex-shrink-0">
    <p class="text-xs font-semibold text-muted-foreground/70 uppercase tracking-wide mb-4">Стан</p>
    <div class="flex flex-col gap-3">
      <Field>
        <FieldLabel>Ім'я *</FieldLabel>
        <Input :model-value="state.name" @update:model-value="update('name', $event)" />
      </Field>
      <Field>
        <FieldLabel>Позначка</FieldLabel>
        <Input :model-value="state.label" @update:model-value="update('label', $event)" />
      </Field>
      <div class="flex flex-col gap-1">
        <label class="text-sm font-medium text-foreground">Колір</label>
        <input
          type="color"
          :value="state.color || '#6b7280'"
          class="w-full h-9 rounded border border-border cursor-pointer"
          @input="update('color', ($event.target as HTMLInputElement).value)"
        />
      </div>
      <label class="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          :checked="!!state.is_initial"
          class="rounded"
          @change="update('is_initial', ($event.target as HTMLInputElement).checked)"
        />
        <span class="text-sm">Початковий</span>
      </label>
      <label class="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          :checked="!!state.is_final"
          class="rounded"
          @change="update('is_final', ($event.target as HTMLInputElement).checked)"
        />
        <span class="text-sm">Фінальний</span>
      </label>
      <Button variant="destructive" size="sm" @click="emit('remove')">Видалити стан</Button>
    </div>
  </div>
</template>
