<script setup lang="ts">
import { ref, onMounted } from 'vue'
import type { DocType } from '@/types'
import { docsApi } from '@/core/api/docs'
import type { WorkflowTransitionItem } from '@/core/api/docs'
import GBadge from '@/components/ui/GBadge.vue'
import GButton from '@/components/ui/GButton.vue'

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
    class="flex items-center gap-3 px-4 py-2.5 bg-[--grunt-surface-secondary] border border-[--grunt-border] rounded-[--grunt-radius-md] mb-4"
  >
    <span class="text-sm text-[--grunt-text-secondary]">Стан:</span>
    <GBadge :label="(doc[doctype.workflow.state_field] as string) ?? '—'" />
    <div class="flex gap-2 ml-2">
      <GButton
        v-for="t in transitions"
        :key="t.action"
        variant="secondary"
        size="sm"
        :loading="isLoading"
        @click="apply(t.action)"
      >
        {{ t.action }}
      </GButton>
    </div>
  </div>
</template>
