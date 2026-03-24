<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useBuilderStore } from '@/stores/builder'
import type { WorkflowState, WorkflowTransition } from '@/types'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { Switch } from '@/components/ui/switch'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Checkbox } from '@/components/ui/checkbox'
import { Trash2 } from 'lucide-vue-next'

const builder = useBuilderStore()

const hasWorkflow = computed(() => !!builder.doctype?.workflow)
const workflow = computed(() => builder.doctype?.workflow ?? { state_field: 'status', states: [], transitions: [] })

// Selection
const selectedStateIndex = ref<number | null>(null)
const selectedTransitionIndex = ref<number | null>(null)

const selectedState = computed(() =>
  selectedStateIndex.value !== null ? workflow.value.states[selectedStateIndex.value] ?? null : null
)
const selectedTransition = computed(() =>
  selectedTransitionIndex.value !== null ? workflow.value.transitions[selectedTransitionIndex.value] ?? null : null
)

// SVG layout positions
const LAYOUT_KEY = computed(() => `grunt_workflow_layout_${builder.doctype?.name}`)
const positions = ref<Record<string, { x: number; y: number }>>({})

onMounted(() => loadPositions())

function loadPositions() {
  try {
    const raw = localStorage.getItem(LAYOUT_KEY.value)
    if (raw) positions.value = JSON.parse(raw)
  } catch {
    positions.value = {}
  }
}

function savePositions() {
  localStorage.setItem(LAYOUT_KEY.value, JSON.stringify(positions.value))
}

function getPos(stateName: string): { x: number; y: number } {
  if (!positions.value[stateName]) {
    const idx = workflow.value.states.findIndex(s => s.name === stateName)
    positions.value[stateName] = { x: 80 + idx * 180, y: 100 }
    savePositions()
  }
  return positions.value[stateName]
}

// Toggle workflow
function toggleWorkflow(enabled: boolean) {
  if (enabled) {
    builder.updateDocType({ workflow: { state_field: 'status', states: [], transitions: [] } })
  } else {
    builder.updateDocType({ workflow: null })
    selectedStateIndex.value = null
    selectedTransitionIndex.value = null
  }
}

// State operations
function addState() {
  builder.addWorkflowState()
}

function updateState(idx: number, key: keyof WorkflowState, val: unknown) {
  if (!builder.doctype?.workflow) return
  const states = [...builder.doctype.workflow.states]
  const oldName = states[idx].name
  states[idx] = { ...states[idx], [key]: val }

  let transitions = [...builder.doctype.workflow.transitions]
  if (key === 'name' && oldName !== val) {
    transitions = transitions.map(t => ({
      ...t,
      from_state: t.from_state === oldName ? val as string : t.from_state,
      to_state: t.to_state === oldName ? val as string : t.to_state,
    }))
    if (positions.value[oldName]) {
      positions.value[val as string] = positions.value[oldName]
      delete positions.value[oldName]
      savePositions()
    }
  }
  builder.updateWorkflow({ states, transitions })
}

function removeState(idx: number) {
  builder.removeWorkflowState(idx)
  selectedStateIndex.value = null
}

// Transition operations
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

// SVG dragging
let draggingState: string | null = null
let dragOffset = { x: 0, y: 0 }

function onStateMousedown(e: MouseEvent, stateName: string) {
  draggingState = stateName
  const pos = getPos(stateName)
  const svg = (e.currentTarget as SVGElement).closest('svg')!.getBoundingClientRect()
  dragOffset = { x: e.clientX - svg.left - pos.x, y: e.clientY - svg.top - pos.y }
}

function onSvgMousemove(e: MouseEvent) {
  if (!draggingState) return
  const svg = (e.currentTarget as SVGElement).getBoundingClientRect()
  positions.value[draggingState] = {
    x: Math.max(40, e.clientX - svg.left - dragOffset.x),
    y: Math.max(30, e.clientY - svg.top - dragOffset.y),
  }
}

function onSvgMouseup() {
  if (draggingState) {
    savePositions()
    draggingState = null
  }
}

function selectState(idx: number) {
  selectedStateIndex.value = idx
  selectedTransitionIndex.value = null
}

function selectTransition(idx: number) {
  selectedTransitionIndex.value = idx
  selectedStateIndex.value = null
}

function getTransitionMid(t: WorkflowTransition) {
  const from = getPos(t.from_state)
  const to = getPos(t.to_state)
  return { x: (from.x + to.x) / 2, y: (from.y + to.y) / 2 }
}

const stateNames = computed(() => workflow.value.states.map(s => s.name))
</script>

<template>
  <div class="flex flex-col h-full">
    <!-- Toolbar -->
    <div class="flex items-center gap-3 px-4 py-2 border-b border-border bg-muted/30 shrink-0">
      <div class="flex items-center gap-2">
        <Switch :checked="hasWorkflow" @update:checked="toggleWorkflow" />
        <Label class="text-sm">Workflow увімкнено</Label>
      </div>

      <template v-if="hasWorkflow">
        <Separator orientation="vertical" class="h-5" />
        <Button variant="outline" size="sm" @click="addState">+ Стан</Button>
        <Button variant="outline" size="sm" :disabled="workflow.states.length < 2" @click="addTransition">+ Перехід</Button>
      </template>
    </div>

    <template v-if="hasWorkflow">
      <div class="flex flex-1 overflow-hidden">
        <!-- SVG Canvas -->
        <div class="flex-1 relative overflow-hidden bg-muted/20">
          <svg
            class="w-full h-full cursor-default"
            @mousemove="onSvgMousemove"
            @mouseup="onSvgMouseup"
            @mouseleave="onSvgMouseup"
          >
            <defs>
              <marker id="wf-arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
                <path d="M0,0 L0,6 L8,3 z" class="fill-muted-foreground/50" />
              </marker>
            </defs>

            <!-- Transitions -->
            <g v-for="(t, ti) in workflow.transitions" :key="ti">
              <line
                :x1="getPos(t.from_state).x + 60"
                :y1="getPos(t.from_state).y + 20"
                :x2="getPos(t.to_state).x + 60"
                :y2="getPos(t.to_state).y + 20"
                class="stroke-muted-foreground/40"
                stroke-width="2"
                marker-end="url(#wf-arrow)"
                :stroke-dasharray="selectedTransitionIndex === ti ? '6,3' : 'none'"
                style="cursor: pointer"
                @click="selectTransition(ti)"
              />
              <text
                :x="getTransitionMid(t).x + 60"
                :y="getTransitionMid(t).y + 16"
                text-anchor="middle"
                font-size="11"
                class="fill-muted-foreground cursor-pointer select-none"
                @click="selectTransition(ti)"
              >{{ t.action }}</text>
            </g>

            <!-- States -->
            <g
              v-for="(state, si) in workflow.states"
              :key="state.name"
              :transform="`translate(${getPos(state.name).x}, ${getPos(state.name).y})`"
              class="cursor-pointer"
              @mousedown="onStateMousedown($event, state.name)"
              @click.stop="selectState(si)"
            >
              <rect
                width="120" height="40" rx="8"
                :fill="state.color || '#6b7280'"
                :stroke="selectedStateIndex === si ? 'hsl(var(--primary))' : 'transparent'"
                stroke-width="2"
                fill-opacity="0.15"
              />
              <rect
                width="120" height="40" rx="8"
                fill="transparent"
                :stroke="state.color || '#6b7280'"
                stroke-width="1.5"
              />
              <text
                x="60" y="25" text-anchor="middle"
                font-size="13" font-weight="500"
                :fill="state.color || '#6b7280'"
                class="select-none"
              >{{ state.label || state.name }}</text>
            </g>
          </svg>

          <div
            v-if="workflow.states.length === 0"
            class="absolute inset-0 flex items-center justify-center text-muted-foreground pointer-events-none"
          >
            <p class="text-sm">Додайте стани за допомогою кнопки "+ Стан"</p>
          </div>
        </div>

        <!-- Right panel: edit state or transition -->
        <div v-if="selectedState !== null && selectedStateIndex !== null" class="w-64 shrink-0 border-l border-border bg-card p-4 overflow-y-auto">
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
              <input
                type="color"
                :value="selectedState.color || '#6b7280'"
                class="w-full h-9 rounded-md border border-input cursor-pointer"
                @input="updateState(selectedStateIndex, 'color', ($event.target as HTMLInputElement).value)"
              />
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

        <div v-else-if="selectedTransition !== null && selectedTransitionIndex !== null" class="w-64 shrink-0 border-l border-border bg-card p-4 overflow-y-auto">
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
                rows="3"
                placeholder="Кожна роль з нового рядка"
                class="w-full text-sm border border-input rounded-md px-2 py-1.5 bg-background focus:outline-none focus:ring-1 focus:ring-ring"
                @input="updateTransition(selectedTransitionIndex, 'allowed_roles', ($event.target as HTMLTextAreaElement).value.split('\n').map(r => r.trim()).filter(Boolean))"
              />
            </div>
            <div class="flex flex-col gap-1.5">
              <Label class="text-sm">Умова (Python)</Label>
              <Input :model-value="selectedTransition.condition ?? ''" placeholder="doc.amount > 0" @update:model-value="updateTransition(selectedTransitionIndex, 'condition', $event || null)" />
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

    <!-- Workflow disabled message -->
    <div v-else class="flex-1 flex items-center justify-center text-muted-foreground">
      <p class="text-sm">Увімкніть workflow для налаштування станів і переходів</p>
    </div>
  </div>
</template>
