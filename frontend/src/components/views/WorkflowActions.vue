<script setup lang="ts">
import { useI18n } from 'vue-i18n'
/**
 * Workflow actions in the form header, next to Save: the document's transitions -
 * actions with `placement: 'workflow'` (global_form.js registers one per allowed
 * transition on `on_transitions`; DocType scripts may change or add to them).
 * One transition is a plain button; several become a shadcn ButtonGroup split
 * button (first one as the button, the rest in its dropdown). A transition
 * without its own `variant`/`icon` takes the colour & icon of the state it
 * leads to (the DocType's `status_indicators`). The state itself is shown in
 * the document sidebar.
 */
import { computed } from 'vue'
import { ChevronDown, Loader2 } from '@lucide/vue'
import type { DocType } from '@/types'
import { Button } from '@/components/ui/button'
import { ButtonGroup, ButtonGroupSeparator } from '@/components/ui/button-group'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import WorkflowActionDialog from '@/components/workflow/WorkflowActionDialog.vue'
import ActionIcon from '@/components/views/actions/ActionIcon.vue'
import { actionButtonStyle, type ActionButtonVariant, type ActionRegistry, type ResolvedAction } from '@/core/actions'
import type { FormProxy, WorkflowTransition } from '@/core/scripting/executor'

const { t } = useI18n()

/** The form controller's workflow state (useFormController). */
export interface WorkflowUi {
  /** Transitions allowed now - to style each action by its target state. */
  transitions: WorkflowTransition[]
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

// Tinted outline per indicator colour - the button looks like the badge of the
// state it leads to. Neutral colours stay a plain outline button.
const TINTS: Record<string, string> = {
  success: 'border-green-500/30 bg-green-500/10 text-green-700 hover:bg-green-500/20 hover:text-green-700 dark:text-emerald-400 dark:hover:text-emerald-400',
  info: 'border-blue-500/30 bg-blue-500/10 text-blue-700 hover:bg-blue-500/20 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-400',
  warn: 'border-amber-500/30 bg-amber-500/10 text-amber-700 hover:bg-amber-500/20 hover:text-amber-700 dark:text-amber-400 dark:hover:text-amber-400',
  danger: 'border-red-500/30 bg-red-500/10 text-red-700 hover:bg-red-500/20 hover:text-red-700 dark:text-red-400 dark:hover:text-red-400',
  purple: 'border-violet-500/30 bg-violet-500/10 text-violet-700 hover:bg-violet-500/20 hover:text-violet-700 dark:text-violet-300 dark:hover:text-violet-300',
  pink: 'border-pink-500/30 bg-pink-500/10 text-pink-700 hover:bg-pink-500/20 hover:text-pink-700 dark:text-pink-300 dark:hover:text-pink-300',
}
const TONE: Record<string, string> = {
  success: 'success', green: 'success',
  info: 'info', blue: 'info',
  warn: 'warn', warning: 'warn', yellow: 'warn', orange: 'warn',
  danger: 'danger', red: 'danger',
  purple: 'purple', pink: 'pink',
}
// Just the text colour - for the state icon in the dropdown items.
const ICON_TEXT: Record<string, string> = {
  success: 'text-green-600 dark:text-emerald-400',
  info: 'text-blue-600 dark:text-blue-400',
  warn: 'text-amber-600 dark:text-amber-400',
  danger: 'text-red-600 dark:text-red-400',
  purple: 'text-violet-600 dark:text-violet-300',
  pink: 'text-pink-600 dark:text-pink-300',
}

const actions = props.actions.resolved('workflow')

interface StyledAction extends Omit<ResolvedAction, 'variant'> {
  variant: ActionButtonVariant
  className: string
  /** Target-state tone, for the dropdown item (`danger` -> destructive item). */
  tone: string | null
}

function targetIndicator(a: ResolvedAction) {
  if (!a.id.startsWith('workflow:')) return null
  const transition = props.workflow.transitions.find((t) => `workflow:${t.action}` === a.id)
  if (!transition) return null
  return props.doctype.status_indicators?.find((i) => i.value === transition.to_state) ?? null
}

const styled = computed<StyledAction[]>(() =>
  actions.value.map((a) => {
    const indicator = targetIndicator(a)
    const icon = a.icon ?? indicator?.icon ?? undefined
    if (a.variant) {
      // Set by a script - wins over the state colour.
      const look = actionButtonStyle(a.variant, 'outline')
      return { ...a, icon, ...look, tone: look.variant === 'destructive' ? 'danger' : null }
    }
    const tone = TONE[String(indicator?.color ?? '').toLowerCase()] ?? null
    return { ...a, icon, variant: 'outline', className: tone ? TINTS[tone] : '', tone }
  }),
)

const main = computed(() => styled.value[0] ?? null)
const rest = computed(() => styled.value.slice(1))
// Filled buttons have no border to split them - shadcn puts a separator between.
const needsSeparator = computed(() => main.value?.variant !== 'outline')
</script>

<template>
  <ButtonGroup v-if="main" :aria-label="t('Workflow')">
    <Button
      size="sm"
      :variant="main.variant"
      :class="['gap-1.5', main.className]"
      :disabled="main.disabled || main.busy"
      @click="main.run()"
    >
      <Loader2 v-if="main.busy" class="size-4 animate-spin" />
      <ActionIcon v-else-if="main.icon" :name="main.icon" class="size-4" />
      {{ main.label }}
    </Button>
    <template v-if="rest.length">
      <ButtonGroupSeparator v-if="needsSeparator" />
      <DropdownMenu>
        <DropdownMenuTrigger as-child>
          <Button
            size="sm"
            :variant="main.variant"
            :class="['!px-2', main.className]"
            :aria-label="`${t('Workflow')}: ${t('more')}`"
          >
            <ChevronDown class="size-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" class="min-w-44">
          <DropdownMenuItem
            v-for="item in rest"
            :key="item.id"
            :variant="item.tone === 'danger' ? 'destructive' : 'default'"
            :disabled="item.disabled || item.busy"
            @click="item.run()"
          >
            <Loader2 v-if="item.busy" class="size-4 animate-spin" />
            <ActionIcon v-else-if="item.icon" :name="item.icon" :class="['size-4', item.tone && ICON_TEXT[item.tone]]" />
            {{ item.label }}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </template>
  </ButtonGroup>

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
