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
  <nav class="flex items-center gap-1.5 text-[13px] text-muted-foreground/70 mb-2 transition-opacity hover:opacity-100">
    <router-link :to="`/${workspaceName}`"
      class="flex items-center gap-1 hover:text-primary transition-colors">
      <span v-if="workspaceIcon" class="text-xs">{{ workspaceIcon }}</span>
      <span class="font-medium">{{ workspaceLabel }}</span>
    </router-link>

    <template v-if="doctype">
      <span class="text-muted-foreground/30 font-light px-0.5">/</span>
      <router-link v-if="docId" :to="`/${workspaceName}/list/${doctype}`"
        class="hover:text-primary transition-colors truncate max-w-[150px]">{{ doctypeLabel }}</router-link>
      <span v-else class="text-foreground/90 font-semibold truncate">{{ doctypeLabel }}</span>
    </template>

    <template v-if="docId">
      <span class="text-muted-foreground/30 font-light px-0.5">/</span>
      <span class="text-foreground/90 font-semibold truncate max-w-[200px]">{{ docId }}</span>
    </template>
  </nav>
</template>
