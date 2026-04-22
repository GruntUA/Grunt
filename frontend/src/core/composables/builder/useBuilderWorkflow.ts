import type { Ref } from 'vue'
import type { DocType, WorkflowDef, WorkflowState, WorkflowTransition, WorkflowStep } from '@/types'

interface UseBuilderWorkflowParams {
  doctype: Ref<DocType | null>
  isDirty: Ref<boolean>
}

export function useBuilderWorkflow({ doctype, isDirty }: UseBuilderWorkflowParams) {
  function updateWorkflow(patch: Partial<WorkflowDef>) {
    if (!doctype.value) return
    const wf = doctype.value.workflow ?? { state_field: 'status', states: [], transitions: [], steps: [] }
    doctype.value = { ...doctype.value, workflow: { ...wf, ...patch } }
    isDirty.value = true
  }

  function addWorkflowState(state?: Partial<WorkflowState>) {
    if (!doctype.value) return
    const wf = doctype.value.workflow ?? { state_field: 'status', states: [], transitions: [], steps: [] }
    const newState: WorkflowState = {
      name: state?.name ?? `state_${wf.states.length + 1}`,
      label: state?.label ?? `State ${wf.states.length + 1}`,
      color: state?.color ?? 'gray',
      is_initial: wf.states.length === 0,
      is_final: false,
    }
    updateWorkflow({ states: [...wf.states, newState] })
  }

  function removeWorkflowState(index: number) {
    if (!doctype.value?.workflow) return
    const states = [...doctype.value.workflow.states]
    const removed = states.splice(index, 1)[0]
    const transitions = doctype.value.workflow.transitions.filter(
      (t) => t.from_state !== removed.name && t.to_state !== removed.name
    )
    updateWorkflow({ states, transitions })
  }

  function addWorkflowTransition(transition?: Partial<WorkflowTransition>) {
    if (!doctype.value?.workflow) return
    const wf = doctype.value.workflow
    const newTransition: WorkflowTransition = {
      action: transition?.action ?? 'Action',
      from_state: transition?.from_state ?? (wf.states[0]?.name ?? ''),
      to_state: transition?.to_state ?? (wf.states[1]?.name ?? wf.states[0]?.name ?? ''),
      allowed_roles: transition?.allowed_roles ?? [],
    }
    updateWorkflow({ transitions: [...wf.transitions, newTransition] })
  }

  function removeWorkflowTransition(index: number) {
    if (!doctype.value?.workflow) return
    const transitions = [...doctype.value.workflow.transitions]
    transitions.splice(index, 1)
    updateWorkflow({ transitions })
  }

  function addWorkflowStep(partial?: Partial<WorkflowStep>) {
    if (!doctype.value) return
    const wf = doctype.value.workflow ?? { state_field: 'status', states: [], transitions: [], steps: [] }
    const steps = wf.steps ?? []
    const newStep: WorkflowStep = {
      id: crypto.randomUUID(),
      name: partial?.name ?? `step_${steps.length + 1}`,
      title: partial?.title ?? '',
      step_type: partial?.step_type ?? 'state',
      variable: partial?.variable ?? null,
      sequence: steps.length,
      is_active: true,
      next_steps: [],
      config: {},
    }
    updateWorkflow({ steps: [...steps, newStep] })
    return newStep
  }

  function updateWorkflowStep(id: string, patch: Partial<WorkflowStep>) {
    if (!doctype.value?.workflow) return
    const steps = (doctype.value.workflow.steps ?? []).map((s) =>
      s.id === id ? { ...s, ...patch } : s
    )
    updateWorkflow({ steps })
  }

  function removeWorkflowStep(id: string) {
    if (!doctype.value?.workflow) return
    const steps = (doctype.value.workflow.steps ?? []).filter((s) => s.id !== id)
    const cleaned = steps.map((s) => ({
      ...s,
      next_steps: s.next_steps.filter((nid) => nid !== id && steps.some((x) => x.id === nid)),
    }))
    updateWorkflow({ steps: cleaned })
  }

  function reorderWorkflowSteps(newSteps: WorkflowStep[]) {
    updateWorkflow({ steps: newSteps.map((s, i) => ({ ...s, sequence: i })) })
  }

  return {
    updateWorkflow,
    addWorkflowState,
    removeWorkflowState,
    addWorkflowTransition,
    removeWorkflowTransition,
    addWorkflowStep,
    updateWorkflowStep,
    removeWorkflowStep,
    reorderWorkflowSteps,
  }
}
