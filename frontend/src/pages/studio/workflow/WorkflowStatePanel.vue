<script setup lang="ts">
import type { WorkflowState } from '@/types'

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
  <div class="p-4 border-l border-border bg-background w-64 shrink-0">
    <p class="text-xs font-semibold text-muted-foreground/70 uppercase tracking-wide mb-4">Стан</p>
    <div class="flex flex-col gap-3">
      <div class="flex flex-col gap-1.5">
        <label class="text-sm font-medium text-foreground">Ім'я *</label>
        <InputText :model-value="state.name" class="w-full" @update:model-value="update('name', $event)" />
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-sm font-medium text-foreground">Позначка</label>
        <InputText :model-value="state.label" class="w-full" @update:model-value="update('label', $event)" />
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-sm font-medium text-foreground">Колір</label>
        <input
          type="color"
          :value="state.color || '#6b7280'"
          class="w-full h-9 rounded border border-border cursor-pointer"
          @input="update('color', ($event.target as HTMLInputElement).value)"
        />
      </div>
      <div class="flex items-center gap-2">
        <Checkbox
          binary
          :model-value="!!state.is_initial"
          :input-id="'init-' + state.name"
          @update:model-value="update('is_initial', $event)"
        />
        <label :for="'init-' + state.name" class="text-sm cursor-pointer">Початковий</label>
      </div>
      <div class="flex items-center gap-2">
        <Checkbox
          binary
          :model-value="!!state.is_final"
          :input-id="'final-' + state.name"
          @update:model-value="update('is_final', $event)"
        />
        <label :for="'final-' + state.name" class="text-sm cursor-pointer">Фінальний</label>
      </div>
      <Button severity="danger" size="small" class="mt-2" @click="emit('remove')">Видалити стан</Button>
    </div>
  </div>
</template>
