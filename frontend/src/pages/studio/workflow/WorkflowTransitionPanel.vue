<script setup lang="ts">
import { computed } from 'vue'
import type { WorkflowTransition, WorkflowState } from '@/types'
import { Input } from '@/components/ui/input'
import { FormField } from '@/components/ui/form-field'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Button } from '@/components/ui/button'

const props = defineProps<{
  transition: WorkflowTransition
  states: WorkflowState[]
}>()
const emit = defineEmits<{
  update: [transition: WorkflowTransition]
  remove: []
}>()

const stateOptionsList = computed(() => props.states.map(s => s.name))

function update(key: keyof WorkflowTransition, val: unknown) {
  emit('update', { ...props.transition, [key]: val })
}
</script>

<template>
  <div class="p-4 border-l border-[--grunt-border] bg-[--grunt-surface-secondary] w-64 flex-shrink-0">
    <p class="text-xs font-semibold text-[--grunt-text-muted] uppercase tracking-wide mb-4">Перехід</p>
    <div class="flex flex-col gap-3">
      <FormField label="Дія (назва кнопки) *">
        <template #default="{ id }">
          <Input :id="id" :model-value="transition.action" @update:model-value="update('action', $event)" />
        </template>
      </FormField>
      <FormField label="Зі стану *">
        <template #default="{ id }">
          <Select :model-value="transition.from_state" @update:model-value="update('from_state', $event)">
            <SelectTrigger :id="id">
              <SelectValue placeholder="— оберіть —" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="opt in stateOptionsList" :key="opt" :value="opt">{{ opt }}</SelectItem>
            </SelectContent>
          </Select>
        </template>
      </FormField>
      <FormField label="До стану *">
        <template #default="{ id }">
          <Select :model-value="transition.to_state" @update:model-value="update('to_state', $event)">
            <SelectTrigger :id="id">
              <SelectValue placeholder="— оберіть —" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="opt in stateOptionsList" :key="opt" :value="opt">{{ opt }}</SelectItem>
            </SelectContent>
          </Select>
        </template>
      </FormField>
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
      <FormField label="Умова (Python)">
        <template #default="{ id }">
          <Input :id="id" :model-value="transition.condition ?? ''" placeholder="doc.amount > 0" @update:model-value="update('condition', $event || null)" />
        </template>
      </FormField>
      <Button variant="destructive" size="sm" @click="emit('remove')">Видалити перехід</Button>
    </div>
  </div>
</template>
