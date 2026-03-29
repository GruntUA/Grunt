<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import type { DocType } from '@/types'
import { docsApi } from '@/core/api/docs'
import type { WorkflowTransitionItem } from '@/core/api/docs'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Loader2 } from 'lucide-vue-next'

const props = defineProps<{
  doctype: DocType
  docId: string
  doc: Record<string, unknown>
}>()
const emit = defineEmits<{ transitioned: [] }>()

const colorToBadge: Record<string, { variant: 'default' | 'secondary' | 'destructive' | 'outline'; class?: string }> = {
  gray:   { variant: 'outline' },
  blue:   { variant: 'outline', class: 'border-blue-400 text-blue-700 bg-blue-50' },
  green:  { variant: 'outline', class: 'border-green-500 text-green-700 bg-green-50' },
  yellow: { variant: 'outline', class: 'border-yellow-400 text-yellow-700 bg-yellow-50' },
  orange: { variant: 'outline', class: 'border-orange-400 text-orange-700 bg-orange-50' },
  red:    { variant: 'destructive' },
  purple: { variant: 'outline', class: 'border-purple-400 text-purple-700 bg-purple-50' },
  pink:   { variant: 'outline', class: 'border-pink-400 text-pink-700 bg-pink-50' },
}

const stateBadge = computed(() => {
  const stateField = props.doctype.workflow?.state_field
  if (!stateField) return { variant: 'default' as const, class: undefined, label: '—' }
  const val = String(props.doc[stateField] ?? '—')
  const sc = props.doctype.status_config
  if (sc) {
    const ind = sc.indicators.find(i => i.value === val)
    if (ind) {
      const badge = colorToBadge[ind.color] ?? { variant: 'default' as const }
      return { ...badge, label: ind.label ?? val }
    }
  }
  return { variant: 'default' as const, class: undefined, label: val }
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
    <Badge :variant="stateBadge.variant" :class="stateBadge.class">{{ stateBadge.label }}</Badge>
    <div class="flex gap-2 ml-2">
      <Button
        v-for="t in transitions"
        :key="t.action"
        variant="secondary"
        size="sm"
        :disabled="isLoading"
        @click="apply(t.action)"
      >
        <Loader2 v-if="isLoading" class="size-4 animate-spin" />
        {{ t.action }}
      </Button>
    </div>
  </div>
</template>
