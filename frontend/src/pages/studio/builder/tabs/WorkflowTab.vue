<script setup lang="ts">
import { ref, computed } from 'vue'
import { useBuilderStore } from '@/stores/builder'
import type { WorkflowState, WorkflowTransition, WorkflowStep, WorkflowStepType } from '@/types'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { Switch } from '@/components/ui/switch'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Checkbox } from '@/components/ui/checkbox'
import { Trash2, Plus, GitBranch, List, ChevronDown, GripVertical, X } from 'lucide-vue-next'
import WorkflowGraph from '@/components/views/WorkflowGraph.vue'

const builder = useBuilderStore()

const hasWorkflow = computed(() => !!builder.doctype?.workflow)
const workflow = computed(() => builder.doctype?.workflow ?? { state_field: 'status', states: [], transitions: [], steps: [] })

// View toggle: 'graph' | 'steps'
const view = ref<'graph' | 'steps'>('graph')

// ── Graph view state ───────────────────────────────────────────────────────

const selectedStateIndex = ref<number | null>(null)
const selectedTransitionIndex = ref<number | null>(null)

const selectedState = computed(() =>
  selectedStateIndex.value !== null ? workflow.value.states[selectedStateIndex.value] ?? null : null
)
const selectedTransition = computed(() =>
  selectedTransitionIndex.value !== null ? workflow.value.transitions[selectedTransitionIndex.value] ?? null : null
)

const positions = computed(() => workflow.value.positions ?? {})

function onUpdatePositions(newPositions: Record<string, { x: number; y: number }>) {
  builder.updateWorkflow({ positions: newPositions })
}

function onGraphConnect(connection: { from: string; to: string }) {
  builder.addWorkflowTransition({
    from_state: connection.from,
    to_state: connection.to,
    action: 'Action',
  })
}

function toggleWorkflow(enabled: boolean) {
  if (enabled) {
    builder.updateDocType({ workflow: { state_field: 'status', states: [], transitions: [], steps: [] } })
  } else {
    builder.updateDocType({ workflow: null })
    selectedStateIndex.value = null
    selectedTransitionIndex.value = null
  }
}

function addState() { builder.addWorkflowState() }

function updateState(idx: number, key: keyof WorkflowState, val: unknown) {
  if (!builder.doctype?.workflow) return
  const states = [...builder.doctype.workflow.states]
  const oldName = states[idx].name
  states[idx] = { ...states[idx], [key]: val }
  let transitions = [...builder.doctype.workflow.transitions]
  const patch: Record<string, unknown> = { states, transitions }
  if (key === 'name' && oldName !== val) {
    transitions = transitions.map(t => ({
      ...t,
      from_state: t.from_state === oldName ? val as string : t.from_state,
      to_state: t.to_state === oldName ? val as string : t.to_state,
    }))
    patch.transitions = transitions
    // Rename position key
    const pos = { ...positions.value }
    if (pos[oldName]) {
      pos[val as string] = pos[oldName]
      delete pos[oldName]
      patch.positions = pos
    }
  }
  builder.updateWorkflow(patch)
}

function removeState(idx: number) {
  builder.removeWorkflowState(idx)
  selectedStateIndex.value = null
}

function addTransition() {
  if (workflow.value.states.length < 2) return
  builder.addWorkflowTransition()
}

function updateTransition(idx: number, key: keyof WorkflowTransition, val: unknown) {
  if (!builder.doctype?.workflow) return
  const transitions = [...builder.doctype.workflow.transitions]
  transitions[idx] = { ...transitions[idx], [key]: val }
  builder.updateWorkflow({ transitions })
}

function removeTransition(idx: number) {
  builder.removeWorkflowTransition(idx)
  selectedTransitionIndex.value = null
}

function selectState(idx: number) { selectedStateIndex.value = idx; selectedTransitionIndex.value = null }
function selectTransition(idx: number) { selectedTransitionIndex.value = idx; selectedStateIndex.value = null }

const stateNames = computed(() => workflow.value.states.map(s => s.name).filter(Boolean))

// ── Steps view state ───────────────────────────────────────────────────────

const selectedStepId = ref<string | null>(null)
const showInactive = ref(false)
const stepFilter = ref('')
const showAddMenu = ref(false)

const selectedStep = computed(() =>
  selectedStepId.value
    ? (workflow.value.steps ?? []).find(s => s.id === selectedStepId.value) ?? null
    : null
)

const STEP_TYPES: { value: WorkflowStepType; label: string; color: string }[] = [
  { value: 'state',        label: 'Стан',                  color: '#6b7280' },
  { value: 'form',         label: 'Форма',                 color: '#3b82f6' },
  { value: 'approval',     label: 'Погодження',            color: '#f59e0b' },
  { value: 'notification', label: 'Повідомлення',          color: '#8b5cf6' },
  { value: 'script',       label: 'Скрипт',                color: '#06b6d4' },
  { value: 'condition',    label: 'Умова',                 color: '#ec4899' },
  { value: 'create_doc',   label: 'Створити документ',     color: '#10b981' },
  { value: 'stop',         label: 'Зупинка',               color: '#ef4444' },
]

function stepTypeLabel(t: WorkflowStepType) {
  return STEP_TYPES.find(x => x.value === t)?.label ?? t
}
function stepTypeColor(t: WorkflowStepType) {
  return STEP_TYPES.find(x => x.value === t)?.color ?? '#6b7280'
}

const visibleSteps = computed(() => {
  const steps = (workflow.value.steps ?? [])
    .filter(s => showInactive.value || s.is_active)
    .filter(s => !stepFilter.value || s.title.toLowerCase().includes(stepFilter.value.toLowerCase()) || s.name.toLowerCase().includes(stepFilter.value.toLowerCase()))
    .sort((a, b) => a.sequence - b.sequence)
  return steps
})

// const activeSteps = computed(() => (workflow.value.steps ?? []).filter(s => s.is_active))
const inactiveSteps = computed(() => (workflow.value.steps ?? []).filter(s => !s.is_active))

function addStep(type: WorkflowStepType) {
  showAddMenu.value = false
  const step = builder.addWorkflowStep({ step_type: type })
  if (step) selectedStepId.value = step.id
}

function removeStep(id: string) {
  builder.removeWorkflowStep(id)
  if (selectedStepId.value === id) selectedStepId.value = null
}

function toggleStepActive(id: string, val: boolean) {
  builder.updateWorkflowStep(id, { is_active: val })
}

function updateSelectedStep(patch: Partial<WorkflowStep>) {
  if (!selectedStepId.value) return
  builder.updateWorkflowStep(selectedStepId.value, patch)
}

function stepNextStepObjects(step: WorkflowStep) {
  return step.next_steps
    .map(id => (workflow.value.steps ?? []).find(s => s.id === id))
    .filter(Boolean) as WorkflowStep[]
}

function removeNextStep(step: WorkflowStep, targetId: string) {
  builder.updateWorkflowStep(step.id, { next_steps: step.next_steps.filter(id => id !== targetId) })
}

function addNextStep(stepId: string, targetId: string) {
  const step = (workflow.value.steps ?? []).find(s => s.id === stepId)
  if (!step || step.next_steps.includes(targetId) || stepId === targetId) return
  builder.updateWorkflowStep(stepId, { next_steps: [...step.next_steps, targetId] })
}

// Step sequence number (among all steps sorted by sequence)
function stepSeq(step: WorkflowStep) {
  const all = [...(workflow.value.steps ?? [])].sort((a, b) => a.sequence - b.sequence)
  return all.findIndex(s => s.id === step.id) + 1
}

// Next-step select dropdown per row
const openNextStepMenu = ref<string | null>(null)

function toggleNextStepMenu(id: string) {
  openNextStepMenu.value = openNextStepMenu.value === id ? null : id
}
</script>

<template>
  <div class="flex flex-col h-full">
    <!-- Toolbar -->
    <div class="flex items-center gap-3 px-4 py-2 border-b border-border bg-muted/30 shrink-0 flex-wrap">
      <div class="flex items-center gap-2">
        <Switch :model-value="hasWorkflow" @update:model-value="toggleWorkflow" />
        <Label class="text-sm">Workflow</Label>
      </div>

      <template v-if="hasWorkflow">
        <Separator orientation="vertical" class="h-5" />

        <!-- View toggle -->
        <div class="flex rounded-lg border border-border overflow-hidden text-xs">
          <button
            :class="['px-3 py-1.5 flex items-center gap-1.5 transition-colors', view === 'graph' ? 'bg-primary text-primary-foreground' : 'hover:bg-muted']"
            @click="view = 'graph'">
            <GitBranch class="w-3.5 h-3.5" /> Діаграма
          </button>
          <button
            :class="['px-3 py-1.5 flex items-center gap-1.5 transition-colors border-l border-border', view === 'steps' ? 'bg-primary text-primary-foreground' : 'hover:bg-muted']"
            @click="view = 'steps'">
            <List class="w-3.5 h-3.5" /> Кроки
          </button>
        </div>

        <template v-if="view === 'graph'">
          <Button variant="outline" size="sm" @click="addState">+ Стан</Button>
          <Button variant="outline" size="sm" :disabled="workflow.states.length < 2" @click="addTransition">+ Перехід</Button>
        </template>
      </template>
    </div>

    <template v-if="hasWorkflow">

      <!-- ══ STEPS VIEW ════════════════════════════════════════════════════ -->
      <div v-if="view === 'steps'" class="flex flex-1 overflow-hidden">

        <!-- Left: step list -->
        <div class="flex-1 flex flex-col overflow-hidden">

          <!-- Steps toolbar -->
          <div class="flex items-center gap-3 px-4 py-2.5 border-b bg-background shrink-0">
            <!-- Add step button with dropdown -->
            <div class="relative">
              <Button size="sm" class="gap-1.5" @click="showAddMenu = !showAddMenu">
                <Plus class="w-3.5 h-3.5" /> Додати крок
                <ChevronDown class="w-3 h-3" />
              </Button>
              <div v-if="showAddMenu"
                class="absolute top-full left-0 mt-1 w-48 bg-card border rounded-xl shadow-lg z-30 overflow-hidden py-1">
                <button
                  v-for="t in STEP_TYPES" :key="t.value"
                  class="w-full px-3 py-2 text-sm text-left hover:bg-muted flex items-center gap-2"
                  @click="addStep(t.value)">
                  <span class="w-2 h-2 rounded-full flex-shrink-0" :style="{ background: t.color }" />
                  {{ t.label }}
                </button>
              </div>
            </div>

            <!-- Show inactive toggle -->
            <label class="flex items-center gap-2 text-sm cursor-pointer select-none ml-2">
              <Switch v-model="showInactive" />
              Показувати неактивні
            </label>

            <!-- Filter -->
            <div class="ml-auto">
              <Input v-model="stepFilter" placeholder="Фільтр…" class="h-8 w-44 text-sm" />
            </div>
          </div>

          <!-- Table header -->
          <div class="grid grid-cols-[32px_1fr_1fr_40px_1fr] gap-0 text-xs font-semibold text-muted-foreground border-b px-4 py-2 bg-muted/20 shrink-0">
            <span />
            <span>Крок</span>
            <span>Заголовок</span>
            <span class="text-center">Акт.</span>
            <span>Наступні кроки</span>
          </div>

          <!-- Step rows -->
          <div class="flex-1 overflow-y-auto">
            <!-- Active steps -->
            <div
              v-for="step in visibleSteps.filter(s => s.is_active)"
              :key="step.id"
              :class="[
                'grid grid-cols-[32px_1fr_1fr_40px_1fr] gap-0 items-center px-4 py-2.5 border-b border-border/50 transition-colors cursor-pointer group',
                selectedStepId === step.id ? 'bg-primary/5 border-primary/20' : 'hover:bg-muted/40',
              ]"
              @click="selectedStepId = step.id"
            >
              <!-- Drag handle -->
              <GripVertical class="w-3.5 h-3.5 text-muted-foreground/30 group-hover:text-muted-foreground cursor-grab" />

              <!-- Step type + name -->
              <div>
                <div class="flex items-center gap-1.5">
                  <span class="w-2 h-2 rounded-full flex-shrink-0" :style="{ background: stepTypeColor(step.step_type) }" />
                  <span class="text-xs font-medium">{{ stepSeq(step) }} {{ stepTypeLabel(step.step_type) }}</span>
                </div>
                <div v-if="step.variable" class="text-[11px] text-muted-foreground italic ml-3.5 mt-0.5">{{ step.variable }}</div>
              </div>

              <!-- Title -->
              <div class="text-sm truncate pr-2">{{ step.title || '—' }}</div>

              <!-- Active checkbox -->
              <div class="flex justify-center" @click.stop>
                <Checkbox :checked="step.is_active" @update:checked="toggleStepActive(step.id, $event)" />
              </div>

              <!-- Next steps -->
              <div class="flex items-center gap-1.5 flex-wrap" @click.stop>
                <div
                  v-for="ns in stepNextStepObjects(step)"
                  :key="ns.id"
                  class="flex items-center gap-0.5 pl-2 pr-1 py-0.5 rounded-full text-[11px] font-medium text-white"
                  :style="{ background: stepTypeColor(ns.step_type) }">
                  {{ stepSeq(ns) }} {{ ns.title || ns.name }}
                  <button class="ml-0.5 opacity-70 hover:opacity-100" @click.stop="removeNextStep(step, ns.id)">
                    <X class="w-3 h-3" />
                  </button>
                </div>

                <!-- Add next step -->
                <div class="relative">
                  <button
                    class="w-5 h-5 rounded-full border border-dashed border-muted-foreground/40 text-muted-foreground/40 hover:border-primary hover:text-primary flex items-center justify-center transition-colors"
                    @click.stop="toggleNextStepMenu(step.id)">
                    <Plus class="w-3 h-3" />
                  </button>
                  <div v-if="openNextStepMenu === step.id"
                    class="absolute top-full left-0 mt-1 w-52 bg-card border rounded-xl shadow-lg z-30 overflow-hidden py-1 max-h-48 overflow-y-auto">
                    <button
                      v-for="target in (workflow.steps ?? []).filter(s => s.id !== step.id && !step.next_steps.includes(s.id))"
                      :key="target.id"
                      class="w-full px-3 py-1.5 text-sm text-left hover:bg-muted flex items-center gap-2"
                      @click.stop="addNextStep(step.id, target.id); openNextStepMenu = null">
                      <span class="w-2 h-2 rounded-full flex-shrink-0" :style="{ background: stepTypeColor(target.step_type) }" />
                      {{ stepSeq(target) }} {{ target.title || target.name }}
                    </button>
                    <p v-if="!(workflow.steps ?? []).filter(s => s.id !== step.id && !step.next_steps.includes(s.id)).length"
                      class="px-3 py-2 text-xs text-muted-foreground">Немає доступних кроків</p>
                  </div>
                </div>
              </div>
            </div>

            <!-- Inactive steps section -->
            <template v-if="showInactive && inactiveSteps.length > 0">
              <div class="px-4 py-2 bg-muted/10 border-b border-dashed">
                <p class="text-xs text-muted-foreground font-medium">Кроки, які не беруть участь у процесі виконання</p>
              </div>
              <div
                v-for="step in inactiveSteps"
                :key="step.id"
                :class="[
                  'grid grid-cols-[32px_1fr_1fr_40px_1fr] gap-0 items-center px-4 py-2.5 border-b border-border/30 transition-colors cursor-pointer group opacity-60',
                  selectedStepId === step.id ? 'bg-primary/5' : 'hover:bg-muted/30',
                ]"
                @click="selectedStepId = step.id"
              >
                <GripVertical class="w-3.5 h-3.5 text-muted-foreground/30" />
                <div>
                  <div class="flex items-center gap-1.5">
                    <span class="w-2 h-2 rounded-full flex-shrink-0" :style="{ background: stepTypeColor(step.step_type) }" />
                    <span class="text-xs font-medium">{{ stepSeq(step) }} {{ stepTypeLabel(step.step_type) }}</span>
                  </div>
                  <div v-if="step.variable" class="text-[11px] text-muted-foreground italic ml-3.5 mt-0.5">{{ step.variable }}</div>
                </div>
                <div class="text-sm truncate pr-2 text-muted-foreground italic">{{ step.title || '—' }}</div>
                <div class="flex justify-center" @click.stop>
                  <Checkbox :checked="step.is_active" @update:checked="toggleStepActive(step.id, $event)" />
                </div>
                <div class="flex items-center gap-1 text-amber-600 text-xs">
                  <span v-for="ns in stepNextStepObjects(step)" :key="ns.id"
                    class="px-2 py-0.5 rounded-full text-[11px] font-medium text-white"
                    :style="{ background: stepTypeColor(ns.step_type) }">
                    {{ stepSeq(ns) }} {{ ns.title || ns.name }}
                  </span>
                </div>
              </div>
            </template>

            <!-- Empty -->
            <div v-if="(workflow.steps ?? []).length === 0"
              class="flex flex-col items-center justify-center py-16 text-muted-foreground gap-2">
              <List class="w-10 h-10 opacity-20" />
              <p class="text-sm">Натисніть «Додати крок», щоб розпочати</p>
            </div>
          </div>
        </div>

        <!-- Right: step config panel -->
        <div v-if="selectedStep" class="w-72 shrink-0 border-l border-border bg-card flex flex-col overflow-hidden">
          <div class="flex items-center justify-between px-4 py-3 border-b">
            <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Крок</p>
            <button class="p-1 rounded hover:bg-muted" @click="selectedStepId = null">
              <X class="w-4 h-4" />
            </button>
          </div>

          <div class="flex-1 overflow-y-auto p-4 space-y-4">
            <!-- Type -->
            <div class="space-y-1.5">
              <Label class="text-xs">Тип</Label>
              <div class="grid grid-cols-2 gap-1.5">
                <button
                  v-for="t in STEP_TYPES" :key="t.value"
                  :class="[
                    'flex items-center gap-2 px-2.5 py-2 rounded-lg border text-xs transition-colors',
                    selectedStep.step_type === t.value
                      ? 'border-primary bg-primary/10 text-primary font-medium'
                      : 'hover:bg-muted border-border',
                  ]"
                  @click="updateSelectedStep({ step_type: t.value as WorkflowStepType })">
                  <span class="w-2 h-2 rounded-full flex-shrink-0" :style="{ background: t.color }" />
                  {{ t.label }}
                </button>
              </div>
            </div>

            <!-- Name -->
            <div class="space-y-1.5">
              <Label class="text-xs">Ім'я (slug)</Label>
              <Input :model-value="selectedStep.name" class="h-8 text-sm"
                @update:model-value="updateSelectedStep({ name: $event as string })" />
            </div>

            <!-- Title -->
            <div class="space-y-1.5">
              <Label class="text-xs">Заголовок</Label>
              <Input :model-value="selectedStep.title" class="h-8 text-sm" placeholder="Відображуваний заголовок"
                @update:model-value="updateSelectedStep({ title: $event as string })" />
            </div>

            <!-- Variable -->
            <div class="space-y-1.5">
              <Label class="text-xs">Змінна</Label>
              <Input :model-value="selectedStep.variable ?? ''" class="h-8 text-sm font-mono" placeholder="req.vars.my_field"
                @update:model-value="updateSelectedStep({ variable: ($event as string) || null })" />
            </div>

            <!-- Active -->
            <div class="flex items-center gap-2">
              <Switch :model-value="selectedStep.is_active" @update:model-value="updateSelectedStep({ is_active: $event })" />
              <Label class="text-sm">Активний</Label>
            </div>

            <!-- Next steps (multi) -->
            <div class="space-y-1.5">
              <Label class="text-xs">Наступні кроки</Label>
              <div class="flex flex-wrap gap-1.5 mb-1">
                <div
                  v-for="ns in stepNextStepObjects(selectedStep)"
                  :key="ns.id"
                  class="flex items-center gap-1 pl-2.5 pr-1.5 py-1 rounded-full text-[11px] font-medium text-white"
                  :style="{ background: stepTypeColor(ns.step_type) }">
                  {{ ns.title || ns.name }}
                  <button @click="removeNextStep(selectedStep, ns.id)"><X class="w-3 h-3" /></button>
                </div>
              </div>
              <select
                class="w-full h-8 px-2 rounded-md border bg-background text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                @change="addNextStep(selectedStep.id, ($event.target as HTMLSelectElement).value); ($event.target as HTMLSelectElement).value = ''">
                <option value="">+ Додати наступний крок…</option>
                <option
                  v-for="s in (workflow.steps ?? []).filter(s => s.id !== selectedStep!.id && !selectedStep!.next_steps.includes(s.id))"
                  :key="s.id" :value="s.id">
                  {{ stepSeq(s) }} {{ s.title || s.name }}
                </option>
              </select>
            </div>

            <Separator />
            <Button variant="destructive" size="sm" class="w-full" @click="removeStep(selectedStep.id)">
              <Trash2 class="size-4 mr-1" /> Видалити крок
            </Button>
          </div>
        </div>

        <div v-else class="w-64 shrink-0 border-l border-border flex items-center justify-center text-muted-foreground text-sm p-4 text-center">
          Натисніть на крок для налаштування
        </div>
      </div>

      <!-- ══ GRAPH VIEW ═════════════════════════════════════════════════════ -->
      <div v-else class="flex flex-1 overflow-hidden">
        <!-- Vue Flow Canvas -->
        <div class="flex-1 relative overflow-hidden">
          <WorkflowGraph
            v-if="workflow.states.length > 0"
            :states="workflow.states"
            :transitions="workflow.transitions"
            :selected-state-index="selectedStateIndex"
            :selected-transition-index="selectedTransitionIndex"
            :positions="positions"
            @select-state="selectState"
            @select-transition="selectTransition"
            @update-positions="onUpdatePositions"
            @connect="onGraphConnect"
          />
          <div v-else
            class="absolute inset-0 flex items-center justify-center text-muted-foreground pointer-events-none">
            <p class="text-sm">Додайте стани за допомогою кнопки "+ Стан"</p>
          </div>
        </div>

        <!-- Right panel: state or transition editor -->
        <div v-if="selectedState !== null && selectedStateIndex !== null"
          class="w-64 shrink-0 border-l border-border bg-card p-4 overflow-y-auto">
          <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-4">Стан</p>
          <div class="flex flex-col gap-3">
            <div class="flex flex-col gap-1.5">
              <Label class="text-sm">Ім'я *</Label>
              <Input :model-value="selectedState.name" @update:model-value="updateState(selectedStateIndex, 'name', $event)" />
            </div>
            <div class="flex flex-col gap-1.5">
              <Label class="text-sm">Позначка</Label>
              <Input :model-value="selectedState.label" @update:model-value="updateState(selectedStateIndex, 'label', $event)" />
            </div>
            <div class="flex flex-col gap-1.5">
              <Label class="text-sm">Колір</Label>
              <input type="color" :value="selectedState.color || '#6b7280'"
                class="w-full h-9 rounded-md border border-input cursor-pointer"
                @input="updateState(selectedStateIndex, 'color', ($event.target as HTMLInputElement).value)" />
            </div>
            <div class="flex items-center gap-2">
              <Checkbox :checked="!!selectedState.is_initial" @update:checked="updateState(selectedStateIndex, 'is_initial', $event)" />
              <Label class="text-sm">Початковий</Label>
            </div>
            <div class="flex items-center gap-2">
              <Checkbox :checked="!!selectedState.is_final" @update:checked="updateState(selectedStateIndex, 'is_final', $event)" />
              <Label class="text-sm">Фінальний</Label>
            </div>
            <Separator />
            <Button variant="destructive" size="sm" @click="removeState(selectedStateIndex)">
              <Trash2 class="size-4 mr-1" /> Видалити стан
            </Button>
          </div>
        </div>

        <div v-else-if="selectedTransition !== null && selectedTransitionIndex !== null"
          class="w-64 shrink-0 border-l border-border bg-card p-4 overflow-y-auto">
          <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-4">Перехід</p>
          <div class="flex flex-col gap-3">
            <div class="flex flex-col gap-1.5">
              <Label class="text-sm">Дія (кнопка) *</Label>
              <Input :model-value="selectedTransition.action" @update:model-value="updateTransition(selectedTransitionIndex, 'action', $event)" />
            </div>
            <div class="flex flex-col gap-1.5">
              <Label class="text-sm">Зі стану *</Label>
              <Select :model-value="selectedTransition.from_state" @update:model-value="updateTransition(selectedTransitionIndex, 'from_state', $event)">
                <SelectTrigger><SelectValue placeholder="— оберіть —" /></SelectTrigger>
                <SelectContent>
                  <SelectItem v-for="s in stateNames" :key="s" :value="s">{{ s }}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div class="flex flex-col gap-1.5">
              <Label class="text-sm">До стану *</Label>
              <Select :model-value="selectedTransition.to_state" @update:model-value="updateTransition(selectedTransitionIndex, 'to_state', $event)">
                <SelectTrigger><SelectValue placeholder="— оберіть —" /></SelectTrigger>
                <SelectContent>
                  <SelectItem v-for="s in stateNames" :key="s" :value="s">{{ s }}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div class="flex flex-col gap-1.5">
              <Label class="text-sm">Дозволені ролі</Label>
              <textarea
                :value="(selectedTransition.allowed_roles ?? []).join('\n')"
                rows="3" placeholder="Кожна роль з нового рядка"
                class="w-full text-sm border border-input rounded-md px-2 py-1.5 bg-background focus:outline-none focus:ring-1 focus:ring-ring"
                @input="updateTransition(selectedTransitionIndex, 'allowed_roles', ($event.target as HTMLTextAreaElement).value.split('\n').map(r => r.trim()).filter(Boolean))"
              />
            </div>
            <div class="flex flex-col gap-1.5">
              <Label class="text-sm">Умова (Python)</Label>
              <Input :model-value="selectedTransition.condition ?? ''" placeholder="doc.amount > 0"
                @update:model-value="updateTransition(selectedTransitionIndex, 'condition', $event || null)" />
            </div>
            <Separator />
            <Button variant="destructive" size="sm" @click="removeTransition(selectedTransitionIndex)">
              <Trash2 class="size-4 mr-1" /> Видалити перехід
            </Button>
          </div>
        </div>

        <div v-else class="w-64 shrink-0 border-l border-border flex items-center justify-center text-muted-foreground text-sm p-4 text-center">
          Натисніть на стан або перехід для редагування
        </div>
      </div>
    </template>

    <div v-else class="flex-1 flex items-center justify-center text-muted-foreground">
      <p class="text-sm">Увімкніть workflow для налаштування станів і переходів</p>
    </div>
  </div>
</template>
