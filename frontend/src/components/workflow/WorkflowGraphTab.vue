<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref, computed, nextTick, watch } from 'vue'
import { VueFlow, useVueFlow, Position, MarkerType } from '@vue-flow/core'
import { Controls } from '@vue-flow/controls'
import { Background } from '@vue-flow/background'
import type { Node, Edge, NodeDragEvent, Connection } from '@vue-flow/core'
import type { DocType } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Checkbox } from '@/components/ui/checkbox'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Plus, Trash2 } from '@lucide/vue'

import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'

const { t } = useI18n()

interface WorkflowStateRow {
  state: string
  label?: string
  color?: string
  is_initial?: boolean
  is_final?: boolean
}

interface WorkflowTransitionRow {
  from_state: string
  to_state: string
  action: string
  allowed_roles?: string
  condition?: string | null
  prompt_fields?: string | null
}

type NodePositions = Record<string, { x: number; y: number }>

const props = defineProps<{
  doctype?: DocType
  modelValue?: Record<string, unknown>
}>()
const emit = defineEmits<{ 'update:modelValue': [value: Record<string, unknown>] }>()

const states = computed<WorkflowStateRow[]>(() => (props.modelValue?.states as WorkflowStateRow[]) ?? [])
const transitions = computed<WorkflowTransitionRow[]>(
  () => (props.modelValue?.transitions as WorkflowTransitionRow[]) ?? []
)
const positions = computed<NodePositions>(() => (props.modelValue?.positions as NodePositions) ?? {})

function patch(partial: Record<string, unknown>) {
  emit('update:modelValue', { ...props.modelValue, ...partial })
}

// ── Color scheme ─────────────────────────────────────────────────────────

const COLOR_SCHEMES: Record<string, { bg: string; border: string; text: string }> = {
  gray: { bg: '#f3f4f6', border: '#9ca3af', text: '#374151' },
  blue: { bg: '#dbeafe', border: '#3b82f6', text: '#1e40af' },
  green: { bg: '#dcfce7', border: '#22c55e', text: '#166534' },
  yellow: { bg: '#fef9c3', border: '#eab308', text: '#854d0e' },
  orange: { bg: '#ffedd5', border: '#f97316', text: '#9a3412' },
  red: { bg: '#fee2e2', border: '#ef4444', text: '#991b1b' },
}

function nodeStyle(state: WorkflowStateRow, isSelected: boolean) {
  const scheme = COLOR_SCHEMES[state.color || 'gray'] ?? COLOR_SCHEMES.gray
  return {
    background: scheme.bg,
    border: `2px solid ${isSelected ? 'var(--primary)' : scheme.border}`,
    borderRadius: '8px',
    color: scheme.text,
    fontWeight: '500',
    fontSize: '13px',
    padding: '8px 16px',
    minWidth: '110px',
    textAlign: 'center' as const,
  }
}

// ── Selection ────────────────────────────────────────────────────────────

const selectedStateIdx = ref<number | null>(null)
const selectedTransitionIdx = ref<number | null>(null)
const selectedState = computed(() =>
  selectedStateIdx.value !== null ? states.value[selectedStateIdx.value] : null
)
const selectedTransition = computed(() =>
  selectedTransitionIdx.value !== null ? transitions.value[selectedTransitionIdx.value] : null
)

// ── Vue Flow nodes/edges ─────────────────────────────────────────────────

const { getNodes, fitView } = useVueFlow({ id: 'workflow-graph-tab' })

const flowNodes = ref<Node[]>([])
const flowEdges = ref<Edge[]>([])

function resolvePosition(stateValue: string, idx: number): { x: number; y: number } {
  const existing = getNodes.value.find(n => n.id === stateValue)
  if (existing) return { x: existing.position.x, y: existing.position.y }
  if (positions.value[stateValue]) return { ...positions.value[stateValue] }
  return { x: 80 + idx * 180, y: 140 }
}

function statesKey() {
  return JSON.stringify(states.value.map(s => [s.state, s.label, s.color, s.is_initial, s.is_final]))
}

watch(statesKey, () => {
  flowNodes.value = states.value.map((state, idx) => ({
    id: state.state,
    position: resolvePosition(state.state, idx),
    label: state.label || state.state,
    type: 'default',
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    style: nodeStyle(state, selectedStateIdx.value === idx),
  }))
}, { immediate: true })

watch(selectedStateIdx, () => {
  flowNodes.value = flowNodes.value.map((n, i) => ({
    ...n,
    style: states.value[i] ? nodeStyle(states.value[i], selectedStateIdx.value === i) : n.style,
  }))
})

function buildEdges(): Edge[] {
  return transitions.value.map((t, idx) => ({
    id: `e-${t.from_state}-${t.to_state}-${idx}`,
    source: t.from_state,
    target: t.to_state,
    label: t.action,
    type: 'smoothstep',
    animated: selectedTransitionIdx.value === idx,
    markerEnd: { type: MarkerType.ArrowClosed, color: '#9ca3af' },
    style: {
      stroke: selectedTransitionIdx.value === idx ? 'var(--primary)' : '#9ca3af',
      strokeWidth: selectedTransitionIdx.value === idx ? 2.5 : 1.5,
    },
    labelStyle: { fontSize: '11px', fill: '#6b7280' },
    labelBgStyle: { fill: 'var(--background)', fillOpacity: 0.85 },
    data: { index: idx },
  }))
}

watch(
  () => [transitions.value, selectedTransitionIdx.value] as const,
  () => { flowEdges.value = buildEdges() },
  { immediate: true, deep: true },
)

watch(() => states.value.length, async () => {
  await nextTick()
  setTimeout(() => fitView({ padding: 0.3 }), 50)
})

// ── Interactions ─────────────────────────────────────────────────────────

function selectState(idx: number) {
  selectedStateIdx.value = idx
  selectedTransitionIdx.value = null
}

function selectTransition(idx: number) {
  selectedTransitionIdx.value = idx
  selectedStateIdx.value = null
}

function onNodeClick(event: { node: { id: string } }) {
  const idx = states.value.findIndex(s => s.state === event.node.id)
  if (idx !== -1) selectState(idx)
}

function onEdgeClick(event: { edge: { data?: { index?: number } } }) {
  const idx = event.edge.data?.index
  if (idx !== undefined) selectTransition(idx)
}

function onNodeDragStop(_event: NodeDragEvent) {
  const next: NodePositions = { ...positions.value }
  for (const node of getNodes.value) {
    next[node.id] = { x: node.position.x, y: node.position.y }
  }
  patch({ positions: next })
}

function onConnect(connection: Connection) {
  if (!connection.source || !connection.target) return
  patch({
    transitions: [
      ...transitions.value,
      { from_state: connection.source, to_state: connection.target, action: t('Transition'), allowed_roles: '' },
    ],
  })
}

// ── Add / edit / remove ──────────────────────────────────────────────────

function addState() {
  const value = `state_${states.value.length + 1}`
  patch({ states: [...states.value, { state: value, label: value, color: 'gray' }] })
}

function addTransition() {
  if (states.value.length < 2) return
  patch({
    transitions: [
      ...transitions.value,
      {
        from_state: states.value[0].state,
        to_state: states.value[1].state,
        action: t('Transition'),
        allowed_roles: '',
      },
    ],
  })
}

function updateSelectedState(partial: Partial<WorkflowStateRow>) {
  if (selectedStateIdx.value === null) return
  const idx = selectedStateIdx.value
  const oldValue = states.value[idx].state
  const nextStates = states.value.map((s, i) => (i === idx ? { ...s, ...partial } : s))

  let nextTransitions = transitions.value
  let nextPositions = positions.value
  if (partial.state !== undefined && partial.state !== oldValue) {
    nextTransitions = transitions.value.map(t => ({
      ...t,
      from_state: t.from_state === oldValue ? partial.state! : t.from_state,
      to_state: t.to_state === oldValue ? partial.state! : t.to_state,
    }))
    if (positions.value[oldValue]) {
      const { [oldValue]: moved, ...rest } = positions.value
      nextPositions = { ...rest, [partial.state]: moved }
    }
  }
  patch({ states: nextStates, transitions: nextTransitions, positions: nextPositions })
}

function removeSelectedState() {
  if (selectedStateIdx.value === null) return
  const value = states.value[selectedStateIdx.value].state
  patch({
    states: states.value.filter((_, i) => i !== selectedStateIdx.value),
    transitions: transitions.value.filter(t => t.from_state !== value && t.to_state !== value),
  })
  selectedStateIdx.value = null
}

function updateSelectedTransition(partial: Partial<WorkflowTransitionRow>) {
  if (selectedTransitionIdx.value === null) return
  const idx = selectedTransitionIdx.value
  patch({ transitions: transitions.value.map((t, i) => (i === idx ? { ...t, ...partial } : t)) })
}

function removeSelectedTransition() {
  if (selectedTransitionIdx.value === null) return
  patch({ transitions: transitions.value.filter((_, i) => i !== selectedTransitionIdx.value) })
  selectedTransitionIdx.value = null
}
</script>

<template>
  <div class="flex h-[calc(100vh-230px)] overflow-hidden -mx-5 -mb-5 rounded-t-md border-t border-border bg-background">
    <div class="flex-1 relative flex flex-col">
      <div class="flex items-center gap-2 pl-5 pr-3 py-2 border-b border-border bg-muted/30 overflow-x-auto overflow-y-visible shrink-0">
        <Button variant="secondary" size="sm" class="shrink-0" @click="addState"><Plus class="size-3.5" />{{ t('State') }}</Button>
        <Button variant="secondary" size="sm" class="shrink-0" :disabled="states.length < 2" @click="addTransition">
          <Plus class="size-3.5" />{{ t('Transition') }}
        </Button>
        <span class="text-muted-foreground shrink-0 whitespace-nowrap ml-2">
          {{ t('Drag from the edge of a node to another node to create a transition') }}
        </span>
      </div>
      <div class="flex-1 relative">
        <VueFlow
          id="workflow-graph-tab"
          v-model:nodes="flowNodes"
          v-model:edges="flowEdges"
          :default-viewport="{ zoom: 1, x: 0, y: 0 }"
          :min-zoom="0.3"
          :max-zoom="2"
          :snap-to-grid="true"
          :snap-grid="[15, 15]"
          fit-view-on-init
          :fit-view-params="{ padding: 0.3 }"
          class="size-full"
          @node-click="onNodeClick"
          @edge-click="onEdgeClick"
          @node-drag-stop="onNodeDragStop"
          @connect="onConnect"
        >
          <Background />
          <Controls :show-interactive="false" />
        </VueFlow>
        <div v-if="states.length === 0" class="absolute inset-0 flex items-center justify-center pointer-events-none">
          <p class="text-muted-foreground">{{ t('Add states with the «State» button above') }}</p>
        </div>
      </div>
    </div>

    <!-- Properties panel -->
    <div class="w-72 shrink-0 border-l border-border overflow-y-auto p-4">
      <template v-if="selectedState">
        <p class="font-semibold text-muted-foreground uppercase tracking-wide mb-3">{{ t('State') }}</p>
        <div class="flex flex-col gap-3">
          <div class="flex flex-col gap-1.5">
            <label class="font-medium">{{ t('Value (for the state field)') }}</label>
            <Input :model-value="selectedState.state"
              @update:model-value="updateSelectedState({ state: String($event) })" />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="font-medium">{{ t('Name') }}</label>
            <Input :model-value="selectedState.label ?? ''"
              @update:model-value="updateSelectedState({ label: String($event) })" />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="font-medium">{{ t('Color') }}</label>
            <Select :model-value="selectedState.color ?? 'gray'"
              @update:model-value="updateSelectedState({ color: String($event) })">
              <SelectTrigger class="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem v-for="c in Object.keys(COLOR_SCHEMES)" :key="c" :value="c">{{ c }}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div class="flex items-center gap-2">
            <Checkbox :model-value="!!selectedState.is_initial"
              @update:model-value="updateSelectedState({ is_initial: !!$event })" />
            <label class="font-medium">{{ t('Initial state') }}</label>
          </div>
          <div class="flex items-center gap-2">
            <Checkbox :model-value="!!selectedState.is_final"
              @update:model-value="updateSelectedState({ is_final: !!$event })" />
            <label class="font-medium">{{ t('Final state') }}</label>
          </div>
          <Button variant="destructive" size="sm" class="mt-2" @click="removeSelectedState">
            <Trash2 class="size-3.5" />{{ t('Delete state') }}
          </Button>
        </div>
      </template>

      <template v-else-if="selectedTransition">
        <p class="font-semibold text-muted-foreground uppercase tracking-wide mb-3">{{ t('Transition') }}</p>
        <div class="flex flex-col gap-3">
          <div class="flex flex-col gap-1.5">
            <label class="font-medium">{{ t('From state') }}</label>
            <Select :model-value="selectedTransition.from_state"
              @update:model-value="updateSelectedTransition({ from_state: String($event) })">
              <SelectTrigger class="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem v-for="s in states" :key="s.state" :value="s.state">{{ s.label || s.state }}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="font-medium">{{ t('To state') }}</label>
            <Select :model-value="selectedTransition.to_state"
              @update:model-value="updateSelectedTransition({ to_state: String($event) })">
              <SelectTrigger class="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem v-for="s in states" :key="s.state" :value="s.state">{{ s.label || s.state }}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="font-medium">{{ t('Action (button text)') }}</label>
            <Input :model-value="selectedTransition.action"
              @update:model-value="updateSelectedTransition({ action: String($event) })" />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="font-medium">{{ t('Allowed roles (comma-separated)') }}</label>
            <Input :model-value="selectedTransition.allowed_roles ?? ''"
              @update:model-value="updateSelectedTransition({ allowed_roles: String($event) })" />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="font-medium">{{ t('Condition (eval:)') }}</label>
            <Textarea :model-value="selectedTransition.condition ?? ''" rows="3"
              @update:model-value="updateSelectedTransition({ condition: String($event) || null })" />
          </div>
          <div class="flex flex-col gap-1.5">
            <label class="font-medium">{{ t('Dialog fields (comma-separated)') }}</label>
            <Input :model-value="selectedTransition.prompt_fields ?? ''"
              :placeholder="t('e.g. execution_note')"
              @update:model-value="updateSelectedTransition({ prompt_fields: String($event) || null })" />
            <p class="text-muted-foreground text-xs">
              {{ t('If set, a dialog opens before the transition to fill in these document fields.') }}
            </p>
          </div>
          <Button variant="destructive" size="sm" class="mt-2" @click="removeSelectedTransition">
            <Trash2 class="size-3.5" />{{ t('Delete transition') }}
          </Button>
        </div>
      </template>

      <p v-else class="text-muted-foreground text-center mt-8">
        {{ t('Click a state or transition to edit it') }}
      </p>
    </div>
  </div>
</template>
