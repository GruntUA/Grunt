<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import type { DocType } from '@/types'
import { docsApi } from '@/core/api/docs'
import type { WorkflowTransitionItem } from '@/core/api/docs'
import { Loader2 } from '@lucide/vue'

const props = defineProps<{
  doctype: DocType
  docId: string
  doc: Record<string, unknown>
}>()
const emit = defineEmits<{ transitioned: [] }>()

const COLOR_CLASSES: Record<string, string> = {
  gray:   'border-muted-foreground/20 bg-muted/40 text-muted-foreground',
  blue:   'border-blue-500/30 bg-blue-500/10 text-blue-700 dark:text-blue-400',
  green:  'border-green-500/30 bg-green-500/10 text-green-700 dark:text-emerald-400',
  yellow: 'border-yellow-500/30 bg-yellow-500/10 text-yellow-700 dark:text-amber-400',
  orange: 'border-orange-500/30 bg-orange-500/10 text-orange-700 dark:text-orange-400',
  red:    'border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-400',
  purple: 'border-purple-500/30 bg-purple-500/10 text-purple-700 dark:text-purple-400',
  pink:   'border-pink-500/30 bg-pink-500/10 text-pink-700 dark:text-pink-400',
}

const stateBadge = computed(() => {
  const stateField = props.doctype.workflow?.state_field
  if (!stateField) return { colorClass: '', label: '—' }
  const val = String(props.doc[stateField] ?? '—')
  const sc = props.doctype.status_config
  if (sc) {
    const ind = sc.indicators.find(i => i.value === val)
    if (ind) {
      return { colorClass: COLOR_CLASSES[ind.color] ?? '', label: ind.label ?? val }
    }
  }
  return { colorClass: '', label: val }
})

const transitions = ref<WorkflowTransitionItem[]>([])
const isLoading = ref(false)

async function loadTransitions() {
  if (!props.doctype.workflow) return
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
    v-if="doctype.workflow"
    class="flex items-center gap-3 px-6 py-3 border-t border-border/50 bg-muted/30"
  >
    <span class="text-sm text-muted-foreground">Стан:</span>
    <Badge :class="stateBadge.colorClass">{{ stateBadge.label }}</Badge>
    <div class="flex gap-2 ml-2">
      <Button
        v-for="t in transitions"
        :key="t.action" severity="secondary" size="small"
        :disabled="isLoading"
        @click="apply(t.action)"
      >
        <Loader2 v-if="isLoading" class="size-4 animate-spin" />
        {{ t.action }}
      </Button>
    </div>
  </div>
</template>
