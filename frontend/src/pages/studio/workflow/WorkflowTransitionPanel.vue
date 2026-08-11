<script setup lang="ts">
import { computed } from 'vue'
import type { WorkflowTransition, WorkflowState } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'

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
  <div class="p-4 border-l border-border bg-background w-64 shrink-0">
    <p class="text-xs font-semibold text-muted-foreground/70 uppercase tracking-wide mb-4">Перехід</p>
    <div class="flex flex-col gap-3">
      <div class="flex flex-col gap-1.5">
        <label class="text-sm font-medium text-foreground">Дія (назва кнопки) *</label>
        <Input :model-value="transition.action" class="w-full" @update:model-value="update('action', $event)" />
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-sm font-medium text-foreground">Зі стану *</label>
        <Select :model-value="transition.from_state" @update:model-value="update('from_state', $event)">
          <SelectTrigger class="w-full">
            <SelectValue placeholder="— оберіть —" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="opt in stateOptionsList" :key="opt" :value="opt">{{ opt }}</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-sm font-medium text-foreground">До стану *</label>
        <Select :model-value="transition.to_state" @update:model-value="update('to_state', $event)">
          <SelectTrigger class="w-full">
            <SelectValue placeholder="— оберіть —" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="opt in stateOptionsList" :key="opt" :value="opt">{{ opt }}</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-sm font-medium text-foreground">Дозволені ролі</label>
        <Textarea
          :model-value="(transition.allowed_roles ?? []).join('\n')"
          rows="3"
          placeholder="Кожна роль з нового рядка"
          class="w-full text-sm"
          @update:model-value="update('allowed_roles', String($event ?? '').split('\n').map(r => r.trim()).filter(Boolean))"
        />
      </div>
      <div class="flex flex-col gap-1.5">
        <label class="text-sm font-medium text-foreground">Умова (Python)</label>
        <Input :model-value="transition.condition ?? ''" placeholder="doc.amount > 0" class="w-full" @update:model-value="update('condition', $event || null)" />
      </div>
      <Button variant="destructive" size="sm" class="mt-2" @click="emit('remove')">Видалити перехід</Button>
    </div>
  </div>
</template>
