<script setup lang="ts">
import { ref, onMounted } from 'vue'
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
    <Badge>{{ (doc[doctype.workflow.state_field] as string) ?? '—' }}</Badge>
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
