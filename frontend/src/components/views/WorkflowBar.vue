<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import type { DocType } from '@/types'
import { docsApi } from '@/core/api/docs'
import type { WorkflowTransitionItem } from '@/core/api/docs'
import { Loader2 } from '@lucide/vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

const props = defineProps<{
  doctype: DocType
  docId: string
  doc: Record<string, unknown>
}>()
const emit = defineEmits<{ transitioned: [] }>()

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

const transitions = ref<WorkflowTransitionItem[]>([])
const isLoading = ref(false)

async function loadTransitions() {
  if (!props.doctype.workflow_state_field) return
  try {
    const r = await docsApi.getTransitions(props.doctype.name, props.docId)
    transitions.value = r.data ?? []
  } catch {
    // silent
  }
}

async function apply(action: string) {
  isLoading.value = true
  try {
    await docsApi.applyTransition(props.doctype.name, props.docId, action)
    emit('transitioned')
    await loadTransitions()
  } finally {
    isLoading.value = false
  }
}

onMounted(loadTransitions)
</script>

<template>
  <div
    v-if="doctype.workflow_state_field"
    class="flex items-center gap-3 px-6 py-3 border-t border-border/50 bg-muted/30"
  >
    <span class="text-muted-foreground">Стан:</span>
    <Badge :class="stateBadge.colorClass">{{ stateBadge.label }}</Badge>
    <div class="flex gap-2 ml-2">
      <Button variant="secondary" v-for="t in transitions" :key="t.action" size="sm" :disabled="isLoading" @click="apply(t.action)">
        <Loader2 v-if="isLoading" class="size-4 animate-spin" />
        {{ t.action }}
      </Button>
    </div>
  </div>
</template>
