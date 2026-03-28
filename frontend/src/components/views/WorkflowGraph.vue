<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { VueFlow, useVueFlow, Position, MarkerType } from '@vue-flow/core'
import { Controls } from '@vue-flow/controls'
import { Background } from '@vue-flow/background'
import type { Node, Edge, NodeDragEvent, Connection } from '@vue-flow/core'
import type { WorkflowState, WorkflowTransition } from '@/types'

import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'

const props = defineProps<{
  states: WorkflowState[]
  transitions: WorkflowTransition[]
  selectedStateIndex: number | null
  selectedTransitionIndex: number | null
  positions: Record<string, { x: number; y: number }>
}>()

const emit = defineEmits<{
  selectState: [index: number]
  selectTransition: [index: number]
  updatePositions: [positions: Record<string, { x: number; y: number }>]
  connect: [connection: { from: string; to: string }]
}>()

const { fitView, getNodes } = useVueFlow({ id: 'workflow-graph' })

// ── Color helpers ─────────────────────────────────────────────────────────

const colorMap: Record<string, { bg: string; border: string; text: string }> = {
  blue:   { bg: '#dbeafe', border: '#3b82f6', text: '#1e40af' },
  green:  { bg: '#dcfce7', border: '#22c55e', text: '#166534' },
  yellow: { bg: '#fef9c3', border: '#eab308', text: '#854d0e' },
  red:    { bg: '#fee2e2', border: '#ef4444', text: '#991b1b' },
  gray:   { bg: '#f3f4f6', border: '#9ca3af', text: '#374151' },
  purple: { bg: '#f3e8ff', border: '#a855f7', text: '#6b21a8' },
  orange: { bg: '#ffedd5', border: '#f97316', text: '#9a3412' },
  pink:   { bg: '#fce7f3', border: '#ec4899', text: '#9d174d' },
}

function getColorScheme(color: string) {
  if (colorMap[color]) return colorMap[color]
  return { bg: color + '26', border: color, text: color }
}

function getNodeStyle(state: WorkflowState, isSelected: boolean) {
  const scheme = getColorScheme(state.color || 'gray')
  return {
    background: scheme.bg,
    border: `2px solid ${isSelected ? 'hsl(var(--primary))' : scheme.border}`,
    borderRadius: '10px',
    color: scheme.text,
    fontWeight: '500',
    fontSize: '13px',
    padding: '8px 16px',
    minWidth: '100px',
    textAlign: 'center' as const,
    boxShadow: isSelected ? '0 0 0 2px hsl(var(--primary) / 0.3)' : 'none',
  }
}

// ── Internal Vue Flow state ───────────────────────────────────────────────

const flowNodes = ref<Node[]>([])
const flowEdges = ref<Edge[]>([])

// Get the current position of a node — prefer Vue Flow internal state, then props, then default
function resolvePosition(stateName: string, index: number): { x: number; y: number } {
  const vfNode = getNodes.value.find(n => n.id === stateName)
  if (vfNode) return { x: vfNode.position.x, y: vfNode.position.y }
  if (props.positions[stateName]) return { ...props.positions[stateName] }
  return { x: 80 + index * 200, y: 150 }
}

// ── Rebuild nodes when states structurally change ─────────────────────────

// Serialized key for structural changes only (name, label, color, is_initial, is_final)
function statesKey() {
  return JSON.stringify(props.states.map(s => [s.name, s.label, s.color, s.is_initial, s.is_final]))
}

watch(statesKey, () => {
  flowNodes.value = props.states.map((state, idx) => ({
    id: state.name,
    position: resolvePosition(state.name, idx),
    data: { state, index: idx },
    type: 'default',
    label: state.label || state.name,
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    style: getNodeStyle(state, props.selectedStateIndex === idx),
  }))
}, { immediate: true })

// ── Update node styles only when selection changes (no position reset) ────

watch(() => props.selectedStateIndex, () => {
  for (let i = 0; i < flowNodes.value.length; i++) {
    const state = props.states[i]
    if (!state) continue
    flowNodes.value[i] = {
      ...flowNodes.value[i],
      style: getNodeStyle(state, props.selectedStateIndex === i),
    }
  }
})

// ── Rebuild edges when transitions change ─────────────────────────────────

function buildEdges(): Edge[] {
  return props.transitions.map((t, idx) => {
    const isSelected = props.selectedTransitionIndex === idx
    return {
      id: `e-${t.from_state}-${t.to_state}-${idx}`,
      source: t.from_state,
      target: t.to_state,
      label: t.action,
      type: 'smoothstep',
      animated: isSelected,
      markerEnd: { type: MarkerType.ArrowClosed, color: '#9ca3af' },
      style: {
        stroke: isSelected ? 'hsl(var(--primary))' : '#9ca3af',
        strokeWidth: isSelected ? 2.5 : 1.5,
      },
      labelStyle: {
        fontSize: '11px',
        fontWeight: isSelected ? '600' : '400',
        fill: isSelected ? 'hsl(var(--primary))' : '#6b7280',
      },
      labelBgStyle: {
        fill: 'hsl(var(--background))',
        fillOpacity: 0.85,
      },
      data: { index: idx },
    }
  })
}

watch(
  () => [props.transitions, props.selectedTransitionIndex] as const,
  () => { flowEdges.value = buildEdges() },
  { immediate: true, deep: true },
)

// ── Fit view when number of states changes ────────────────────────────────

watch(() => props.states.length, async () => {
  await nextTick()
  setTimeout(() => fitView({ padding: 0.3 }), 100)
})

// ── Event handlers ────────────────────────────────────────────────────────

function onNodeClick(event: { event: MouseEvent; node: Node }) {
  const idx = props.states.findIndex(s => s.name === event.node.id)
  if (idx !== -1) emit('selectState', idx)
}

function onEdgeClick(event: { event: MouseEvent; edge: Edge }) {
  const idx = event.edge.data?.index as number
  if (idx !== undefined) emit('selectTransition', idx)
}

function onNodeDragStop(_event: NodeDragEvent) {
  const newPositions: Record<string, { x: number; y: number }> = {}
  for (const node of getNodes.value) {
    newPositions[node.id] = { x: node.position.x, y: node.position.y }
  }
  emit('updatePositions', newPositions)
}

function onConnect(connection: Connection) {
  if (connection.source && connection.target) {
    emit('connect', { from: connection.source, to: connection.target })
  }
}
</script>

<template>
  <VueFlow
    id="workflow-graph"
    v-model:nodes="flowNodes"
    v-model:edges="flowEdges"
    :default-viewport="{ zoom: 1, x: 0, y: 0 }"
    :min-zoom="0.3"
    :max-zoom="2"
    :snap-to-grid="true"
    :snap-grid="[15, 15]"
    fit-view-on-init
    :fit-view-params="{ padding: 0.3 }"
    :nodes-draggable="true"
    :nodes-connectable="true"
    :edges-updatable="false"
    class="workflow-flow"
    @node-click="onNodeClick"
    @edge-click="onEdgeClick"
    @node-drag-stop="onNodeDragStop"
    @connect="onConnect"
  >
    <Background />
    <Controls :show-fit-view="true" :show-interactive="false" />
  </VueFlow>
</template>

<style>
.workflow-flow {
  width: 100%;
  height: 100%;
}

.workflow-flow .vue-flow__node-default {
  padding: 0;
  border: none;
  border-radius: 0;
  box-shadow: none;
  background: transparent;
}

.workflow-flow .vue-flow__node-default .vue-flow__node-label {
  pointer-events: none;
}

.workflow-flow .vue-flow__edge-label {
  pointer-events: all;
  cursor: pointer;
}

.workflow-flow .vue-flow__controls {
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}
</style>
