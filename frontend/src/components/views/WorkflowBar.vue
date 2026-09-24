<script setup lang="ts">
/**
 * Workflow bar: the document's state (chrome) and its transitions — actions
 * with `placement: 'workflow'` (global_form.js registers one per allowed
 * transition on `on_transitions`; DocType scripts may change or add to them).
 */
import { computed } from 'vue'
import type { DocType } from '@/types'
import { Badge } from '@/components/ui/badge'
import { statusBadgeFor } from '@/core/status'
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

const stateBadge = computed(() => statusBadgeFor(props.doctype, props.doc[props.doctype.workflow_state_field ?? '']))

</script>

<template>
  <div
    v-if="doctype.workflow_state_field"
    class="flex items-center gap-3 px-6 py-3 border-t border-border/50 bg-muted/30"
  >
    <span class="text-muted-foreground">Стан:</span>
    <Badge v-if="stateBadge" variant="outline" :class="stateBadge.class">{{ stateBadge.label }}</Badge>
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
