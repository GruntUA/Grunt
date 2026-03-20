<script setup lang="ts">
import type { WorkflowTransition, WorkflowState } from '@/types'
import GInput from '@/components/ui/GInput.vue'
import GSelect from '@/components/ui/GSelect.vue'
import GButton from '@/components/ui/GButton.vue'

const props = defineProps<{
  transition: WorkflowTransition
  states: WorkflowState[]
}>()
const emit = defineEmits<{
  update: [transition: WorkflowTransition]
  remove: []
}>()

const stateOptions = computed(() => props.states.map(s => s.name).join('\n'))

function update(key: keyof WorkflowTransition, val: unknown) {
  emit('update', { ...props.transition, [key]: val })
}

import { computed } from 'vue'
</script>

<template>
  <div class="p-4 border-l border-[--grunt-border] bg-[--grunt-surface-secondary] w-64 flex-shrink-0">
    <p class="text-xs font-semibold text-[--grunt-text-muted] uppercase tracking-wide mb-4">Перехід</p>
    <div class="flex flex-col gap-3">
      <GInput
        :model-value="transition.action"
        label="Дія (назва кнопки) *"
        @update:model-value="update('action', $event)"
      />
      <GSelect
        :model-value="transition.from_state"
        label="Зі стану *"
        :options="stateOptions"
        @update:model-value="update('from_state', $event)"
      />
      <GSelect
        :model-value="transition.to_state"
        label="До стану *"
        :options="stateOptions"
        @update:model-value="update('to_state', $event)"
      />
      <div class="flex flex-col gap-1">
        <label class="text-sm font-medium text-[--grunt-text-primary]">Дозволені ролі</label>
        <textarea
          :value="(transition.allowed_roles ?? []).join('\n')"
          rows="3"
          placeholder="Кожна роль з нового рядка"
          class="w-full text-sm border border-[--grunt-border] rounded-[--grunt-radius-sm] px-2 py-1.5 focus:outline-none focus:border-[--grunt-primary]"
          @input="update('allowed_roles', ($event.target as HTMLTextAreaElement).value.split('\n').map(r => r.trim()).filter(Boolean))"
        />
      </div>
      <GInput
        :model-value="transition.condition ?? ''"
        label="Умова (Python)"
        placeholder="doc.amount > 0"
        @update:model-value="update('condition', $event || null)"
      />
      <GButton variant="danger" size="sm" @click="emit('remove')">Видалити перехід</GButton>
    </div>
  </div>
</template>
