<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useDocTypeStore } from '@/stores/doctype'
import { metaApi } from '@/core/api'
import { useToast } from '@/core/composables/useToast'
import type { DocType, WorkflowDef, WorkflowState, WorkflowTransition } from '@/types'
import Button from 'primevue/button'
import { Spinner } from '@/components/ui/spinner'
import { Loader2 } from '@lucide/vue'
import WorkflowStatePanel from './WorkflowStatePanel.vue'
import WorkflowTransitionPanel from './WorkflowTransitionPanel.vue'

const route = useRoute()
const dtStore = useDocTypeStore()
const toast = useToast()

const doctypeName = route.params.doctype as string
const dt = ref<DocType | null>(null)
const isLoading = ref(true)
const isSaving = ref(false)
const activeTab = ref<'visual' | 'json'>('visual')
const jsonText = ref('')
const jsonError = ref('')

// Selection
const selectedStateIndex = ref<number | null>(null)
const selectedTransitionIndex = ref<number | null>(null)

// Local workflow copy
const workflow = ref<WorkflowDef>({
  state_field: 'status',
  states: [],
  transitions: [],
  steps: [],
})

// SVG layout — positions stored in localStorage
const LAYOUT_KEY = computed(() => `grunt_workflow_layout_${doctypeName}`)
const positions = ref<Record<string, { x: number; y: number }>>({})

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
    positions.value[stateName] = { x: 80 + idx * 160, y: 120 }
    savePositions()
  }
  return positions.value[stateName]
}

onMounted(async () => {
  loadPositions()
  try {
    dt.value = await dtStore.get(doctypeName)
    if (dt.value?.workflow) {
      workflow.value = JSON.parse(JSON.stringify(dt.value.workflow))
    }
    syncJsonText()
  } finally {
    isLoading.value = false
  }
})

function syncJsonText() {
  jsonText.value = JSON.stringify(workflow.value, null, 2)
  jsonError.value = ''
}

watch(activeTab, (tab) => {
  if (tab === 'json') syncJsonText()
})

function applyJson() {
  try {
    workflow.value = JSON.parse(jsonText.value)
    jsonError.value = ''
    toast.success('JSON застосовано')
    activeTab.value = 'visual'
  } catch (e) {
    jsonError.value = (e as Error).message
  }
}

async function save() {
  if (!dt.value) return
  isSaving.value = true
  try {
    const updated = { ...dt.value, workflow: workflow.value }
    await metaApi.update(updated)
    dtStore.invalidate(doctypeName)
    toast.success('Workflow збережено')
  } catch {
    toast.error('Помилка збереження')
  } finally {
    isSaving.value = false
  }
}

function addState() {
  const name = `State${workflow.value.states.length + 1}`
  workflow.value.states.push({ name, label: name, color: '#6b7280' })
  positions.value[name] = { x: 80 + (workflow.value.states.length - 1) * 160, y: 120 }
  savePositions()
}

function addTransition() {
  if (workflow.value.states.length < 2) {
    toast.error('Потрібно щонайменше 2 стани')
    return
  }
  workflow.value.transitions.push({
    action: 'Перейти',
    from_state: workflow.value.states[0].name,
    to_state: workflow.value.states[1].name,
    allowed_roles: [],
    condition: null,
  })
}

function updateState(idx: number, state: WorkflowState) {
  const oldName = workflow.value.states[idx].name
  workflow.value.states[idx] = state
  // Update transition references
  if (oldName !== state.name) {
    workflow.value.transitions = workflow.value.transitions.map(t => ({
      ...t,
      from_state: t.from_state === oldName ? state.name : t.from_state,
      to_state: t.to_state === oldName ? state.name : t.to_state,
    }))
    if (positions.value[oldName]) {
      positions.value[state.name] = positions.value[oldName]
      delete positions.value[oldName]
      savePositions()
    }
  }
}

function removeState(idx: number) {
  workflow.value.states.splice(idx, 1)
  selectedStateIndex.value = null
}

function updateTransition(idx: number, t: WorkflowTransition) {
  workflow.value.transitions[idx] = t
}

function removeTransition(idx: number) {
  workflow.value.transitions.splice(idx, 1)
  selectedTransitionIndex.value = null
}

// SVG drag
let draggingState: string | null = null
let dragOffset = { x: 0, y: 0 }

function onStateMousedown(e: MouseEvent, stateName: string) {
  draggingState = stateName
  const pos = getPos(stateName)
  dragOffset = { x: e.offsetX - pos.x, y: e.offsetY - pos.y }
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

const selectedState = computed(() =>
  selectedStateIndex.value !== null ? workflow.value.states[selectedStateIndex.value] : null
)
const selectedTransition = computed(() =>
  selectedTransitionIndex.value !== null ? workflow.value.transitions[selectedTransitionIndex.value] : null
)

// Compute mid-point for transition arrows
function getTransitionMid(t: WorkflowTransition) {
  const from = getPos(t.from_state)
  const to = getPos(t.to_state)
  return { x: (from.x + to.x) / 2, y: (from.y + to.y) / 2 }
}
</script>

<template>
  <div class="flex flex-col h-screen">
    <!-- Header -->
    <div class="flex items-center justify-between px-6 py-3 border-b border-border bg-card">
      <div class="flex items-center gap-4">
        <h1 class="text-base font-semibold text-foreground">
          Workflow: {{ doctypeName }}
        </h1>
        <div class="flex border border-border rounded-sm overflow-hidden text-sm">
          <button
            :class="['px-3 py-1.5 transition-colors', activeTab === 'visual' ? 'bg-primary text-white' : 'hover:bg-muted']"
            @click="activeTab = 'visual'"
          >Візуальний</button>
          <button
            :class="['px-3 py-1.5 transition-colors', activeTab === 'json' ? 'bg-primary text-white' : 'hover:bg-muted']"
            @click="activeTab = 'json'"
          >JSON</button>
        </div>
      </div>
      <div class="flex gap-2">
        <Button severity="secondary" size="small" @click="addState">+ Стан</Button>
        <Button severity="secondary" size="small" @click="addTransition">+ Перехід</Button>
        <Button size="small" :disabled="isSaving" @click="save"><Loader2 v-if="isSaving" class="size-4 animate-spin" />Зберегти</Button>
      </div>
    </div>

    <div v-if="isLoading" class="flex-1 flex items-center justify-center">
      <Spinner size="lg" />
    </div>

    <div v-else class="flex flex-1 overflow-hidden">
      <!-- JSON tab -->
      <div v-if="activeTab === 'json'" class="flex-1 flex flex-col p-6 gap-4">
        <textarea
          v-model="jsonText"
          class="flex-1 font-mono text-sm border border-border rounded-md p-4 focus:outline-none focus:border-primary resize-none"
          spellcheck="false"
        />
        <p v-if="jsonError" class="text-sm text-destructive">{{ jsonError }}</p>
        <div class="flex gap-2">
          <Button @click="applyJson">Застосувати</Button>
          <Button severity="secondary" @click="syncJsonText">Скинути</Button>
        </div>
      </div>

      <!-- Visual tab -->
      <template v-else>
        <div class="flex-1 relative overflow-hidden bg-background">
          <svg
            class="w-full h-full cursor-default"
            @mousemove="onSvgMousemove"
            @mouseup="onSvgMouseup"
            @mouseleave="onSvgMouseup"
          >
            <defs>
              <marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
                <path d="M0,0 L0,6 L8,3 z" fill="#9ca3af" />
              </marker>
            </defs>

            <!-- Transitions (lines) -->
            <g v-for="(t, ti) in workflow.transitions" :key="ti">
              <line
                :x1="getPos(t.from_state).x + 60"
                :y1="getPos(t.from_state).y + 20"
                :x2="getPos(t.to_state).x + 60"
                :y2="getPos(t.to_state).y + 20"
                stroke="#9ca3af"
                stroke-width="2"
                marker-end="url(#arrow)"
                :stroke-dasharray="selectedTransitionIndex === ti ? '6,3' : 'none'"
                class="cursor-pointer"
                @click="selectTransition(ti)"
              />
              <!-- Transition label -->
              <text
                :x="getTransitionMid(t).x + 60"
                :y="getTransitionMid(t).y + 16"
                text-anchor="middle"
                font-size="11"
                fill="#6b7280"
                class="cursor-pointer select-none"
                @click="selectTransition(ti)"
              >{{ t.action }}</text>
            </g>

            <!-- States (rects) -->
            <g
              v-for="(state, si) in workflow.states"
              :key="state.name"
              :transform="`translate(${getPos(state.name).x}, ${getPos(state.name).y})`"
              class="cursor-pointer"
              @mousedown="onStateMousedown($event, state.name)"
              @click.stop="selectState(si)"
            >
              <rect
                width="120"
                height="40"
                rx="8"
                :fill="state.color || '#6b7280'"
                :stroke="selectedStateIndex === si ? '#1d4ed8' : 'transparent'"
                stroke-width="2"
                fill-opacity="0.15"
                :stroke-opacity="selectedStateIndex === si ? 1 : 0"
              />
              <rect
                width="120"
                height="40"
                rx="8"
                fill="transparent"
                :stroke="state.color || '#6b7280'"
                stroke-width="1.5"
              />
              <text
                x="60"
                y="25"
                text-anchor="middle"
                font-size="13"
                font-weight="500"
                :fill="state.color || '#6b7280'"
                class="select-none"
              >{{ state.label || state.name }}</text>
            </g>
          </svg>

          <!-- Empty state -->
          <div
            v-if="workflow.states.length === 0"
            class="absolute inset-0 flex flex-col items-center justify-center text-muted-foreground/70 pointer-events-none"
          >
            <p class="text-sm">Додайте стани за допомогою кнопки "&#43; Стан"</p>
          </div>
        </div>

        <!-- Right panel -->
        <WorkflowStatePanel
          v-if="selectedState !== null && selectedStateIndex !== null"
          :state="selectedState"
          @update="updateState(selectedStateIndex, $event)"
          @remove="removeState(selectedStateIndex)"
        />
        <WorkflowTransitionPanel
          v-else-if="selectedTransition !== null && selectedTransitionIndex !== null"
          :transition="selectedTransition"
          :states="workflow.states"
          @update="updateTransition(selectedTransitionIndex, $event)"
          @remove="removeTransition(selectedTransitionIndex)"
        />
        <div
          v-else
          class="w-64 flex-shrink-0 border-l border-border flex items-center justify-center text-muted-foreground/70 text-sm p-4 text-center"
        >
          Натисніть на стан або перехід для редагування
        </div>
      </template>
    </div>
  </div>
</template>
