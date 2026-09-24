<script setup lang="ts">
/**
 * Workflow bar: the document's state (chrome) and its transitions — actions
 * with `placement: 'workflow'` (global_form.js registers one per allowed
 * transition on `on_transitions`; DocType scripts may change or add to them).
 */
import { computed } from 'vue'
import type { DocType } from '@/types'
import { Badge } from '@/components/ui/badge'
import WorkflowActionDialog from '@/components/workflow/WorkflowActionDialog.vue'
import ActionButtons from '@/components/views/actions/ActionButtons.vue'
import type { ActionRegistry } from '@/core/actions'
import type { FormProxy, WorkflowTransition } from '@/core/scripting/executor'

/** The form controller's workflow state (useFormController). */
export interface WorkflowUi {
  pending: WorkflowTransition | null
  error: string | null
  busy: boolean
  apply: (action: string, values?: Record<string, unknown>) => Promise<void>
  close: () => void
}

const props = defineProps<{
  doctype: DocType
  doc: Record<string, unknown>
  actions: ActionRegistry<FormProxy>
  workflow: WorkflowUi
}>()

const transitionActions = props.actions.resolved('workflow')

const COLOR_CLASSES: Record<string, string> = {
  default: '',
  secondary: 'border-muted-foreground/20 bg-muted/40 text-muted-foreground',
  success: 'border-green-500/30 bg-green-500/10 text-green-700 dark:text-emerald-400',
  info: 'border-blue-500/30 bg-blue-500/10 text-blue-700 dark:text-blue-400',
  warn: 'border-yellow-500/30 bg-yellow-500/10 text-yellow-700 dark:text-amber-400',
  danger: 'border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-400',
  contrast: 'border-foreground/20 bg-foreground text-background',
  // Legacy colors for backward compatibility.
  gray: 'border-muted-foreground/20 bg-muted/40 text-muted-foreground',
  blue: 'border-blue-500/30 bg-blue-500/10 text-blue-700 dark:text-blue-400',
  green: 'border-green-500/30 bg-green-500/10 text-green-700 dark:text-emerald-400',
  yellow: 'border-yellow-500/30 bg-yellow-500/10 text-yellow-700 dark:text-amber-400',
  orange: 'border-yellow-500/30 bg-yellow-500/10 text-yellow-700 dark:text-amber-400',
  red: 'border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-400',
  purple: 'border-violet-500/30 bg-violet-500/10 text-violet-700 dark:text-violet-300',
  pink: 'border-pink-500/30 bg-pink-500/10 text-pink-700 dark:text-pink-300',
}

const stateBadge = computed(() => {
  const stateField = props.doctype.workflow_state_field
  if (!stateField) return { colorClass: '', label: '—' }
  const val = String(props.doc[stateField] ?? '—')
  const ind = (props.doctype.status_indicators ?? []).find(i => i.value === val)
  if (ind) {
    return { colorClass: COLOR_CLASSES[ind.color] ?? '', label: ind.label ?? val }
  }
  return { colorClass: '', label: val }
})

</script>

<template>
  <div
    v-if="doctype.workflow_state_field"
    class="flex items-center gap-3 px-6 py-3 border-t border-border/50 bg-muted/30"
  >
    <span class="text-muted-foreground">Стан:</span>
    <Badge :class="stateBadge.colorClass">{{ stateBadge.label }}</Badge>
    <div class="flex gap-2 ml-2">
      <ActionButtons :toolbar="transitionActions" />
    </div>
  </div>

  <WorkflowActionDialog
    v-if="workflow.pending"
    :doctype="doctype"
    :transition="workflow.pending"
    :doc="doc"
    :is-submitting="workflow.busy"
    :error-message="workflow.error"
    @submit="(values) => workflow.apply(workflow.pending!.action, values)"
    @close="workflow.close()"
  />
</template>
