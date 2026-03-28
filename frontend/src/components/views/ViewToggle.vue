<script setup lang="ts">
import {
  LayoutList,
  LayoutGrid,
  CalendarDays as CalendarIcon,
  GitBranch,
} from 'lucide-vue-next'

export type ViewMode = 'list' | 'kanban' | 'calendar' | 'tree'

defineProps<{
  modelValue: ViewMode
  hasKanban: boolean
  hasCalendar: boolean
  hasTree: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: ViewMode]
}>()
</script>

<template>
  <div class="flex rounded-lg border border-border overflow-hidden">
    <button
      class="px-3 py-1.5 text-sm font-medium transition-colors flex items-center gap-1.5"
      :class="modelValue === 'list' ? 'bg-primary text-primary-foreground' : 'bg-card text-muted-foreground hover:text-foreground'"
      @click="emit('update:modelValue', 'list')"
    >
      <LayoutList class="size-4" />
      Список
    </button>
    <button
      v-if="hasKanban"
      class="px-3 py-1.5 text-sm font-medium transition-colors flex items-center gap-1.5 border-l border-border"
      :class="modelValue === 'kanban' ? 'bg-primary text-primary-foreground' : 'bg-card text-muted-foreground hover:text-foreground'"
      @click="emit('update:modelValue', 'kanban')"
    >
      <LayoutGrid class="size-4" />
      Канбан
    </button>
    <button
      v-if="hasCalendar"
      class="px-3 py-1.5 text-sm font-medium transition-colors flex items-center gap-1.5 border-l border-border"
      :class="modelValue === 'calendar' ? 'bg-primary text-primary-foreground' : 'bg-card text-muted-foreground hover:text-foreground'"
      @click="emit('update:modelValue', 'calendar')"
    >
      <CalendarIcon class="size-4" />
      Календар
    </button>
    <button
      v-if="hasTree"
      class="px-3 py-1.5 text-sm font-medium transition-colors flex items-center gap-1.5 border-l border-border"
      :class="modelValue === 'tree' ? 'bg-primary text-primary-foreground' : 'bg-card text-muted-foreground hover:text-foreground'"
      @click="emit('update:modelValue', 'tree')"
    >
      <GitBranch class="size-4" />
      Дерево
    </button>
  </div>
</template>
