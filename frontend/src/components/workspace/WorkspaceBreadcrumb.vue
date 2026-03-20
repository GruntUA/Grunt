<script setup lang="ts">
import { computed } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'

const props = defineProps<{
  workspaceName: string
  doctype?: string
  docId?: string | null
}>()

const wsStore = useWorkspaceStore()

const workspaceLabel = computed(() => wsStore.active?.label ?? props.workspaceName)
const workspaceIcon = computed(() => wsStore.active?.icon ?? '')

const doctypeLabel = computed(() => {
  if (!props.doctype || !wsStore.active) return props.doctype
  const item = wsStore.active.items.find(i => i.link_to === props.doctype)
  return item?.label ?? props.doctype
})
</script>

<template>
  <nav class="flex items-center gap-1.5 text-sm mb-4 text-[--grunt-text-muted]">
    <router-link
      :to="`/${workspaceName}`"
      class="flex items-center gap-1 hover:text-[--grunt-primary] transition-colors"
    >
      <span>{{ workspaceIcon }}</span>
      <span>{{ workspaceLabel }}</span>
    </router-link>

    <template v-if="doctype">
      <span class="text-[--grunt-text-muted]">/</span>
      <router-link
        v-if="docId"
        :to="`/${workspaceName}/list/${doctype}`"
        class="hover:text-[--grunt-primary] transition-colors"
      >{{ doctypeLabel }}</router-link>
      <span v-else class="text-[--grunt-text-secondary]">{{ doctypeLabel }}</span>
    </template>

    <template v-if="docId">
      <span class="text-[--grunt-text-muted]">/</span>
      <span class="text-[--grunt-text-secondary]">{{ docId }}</span>
    </template>
  </nav>
</template>
