<script setup lang="ts">
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import type { WorkspaceLink } from '@/core/api/workspace'
import { Badge } from '@/components/ui/badge'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { Plus } from 'lucide-vue-next'

const props = defineProps<{
  item: WorkspaceLink
  workspaceName: string
  count?: number
  collapsed?: boolean
  color?: string
}>()

const router = useRouter()
const route = useRoute()

const isActive = computed(() => {
  if (props.item.type === 'DocType') {
    return route.params.doctype === props.item.link_to
  }
  if (props.item.type === 'Report') {
    return route.params.reportName === props.item.link_to
  }
  return false
})

function navigate() {
  switch (props.item.type) {
    case 'DocType':
      router.push(`/${props.workspaceName}/list/${props.item.link_to}`)
      break
    case 'Report':
      router.push(`/${props.workspaceName}/report/${props.item.link_to}`)
      break
    case 'URL':
      window.open(props.item.link_to, '_blank')
      break
    case 'Dashboard':
      router.push(`/${props.workspaceName}/dashboard/${props.item.link_to}`)
      break
  }
}

function createNew(e: Event) {
  e.stopPropagation()
  router.push(`/${props.workspaceName}/list/${props.item.link_to}/new`)
}

const displayCount = computed(() => {
  if (!props.count || props.count <= 0) return ''
  return props.count > 99 ? '99+' : String(props.count)
})
</script>

<template>
  <Tooltip v-if="collapsed" :delay-duration="0">
    <TooltipTrigger as-child>
      <button
        class="w-full flex items-center justify-center h-9 rounded-md transition-colors"
        :class="isActive
          ? 'bg-primary/10 text-primary'
          : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'"
        @click="navigate"
      >
        <span class="text-sm">{{ item.icon }}</span>
      </button>
    </TooltipTrigger>
    <TooltipContent side="right" :side-offset="8">
      {{ item.label }}
      <span v-if="displayCount" class="ml-1 text-muted-foreground">({{ displayCount }})</span>
    </TooltipContent>
  </Tooltip>

  <button
    v-else
    class="group w-full flex items-center gap-2.5 px-2.5 h-8 rounded-md text-left transition-colors"
    :class="isActive
      ? 'bg-primary/10 text-primary font-medium'
      : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'"
    @click="navigate"
  >
    <span class="text-sm shrink-0 w-5 text-center">{{ item.icon }}</span>
    <span class="text-sm truncate flex-1">{{ item.label }}</span>

    <!-- Count badge -->
    <Badge
      v-if="displayCount"
      variant="secondary"
      class="h-5 min-w-5 px-1 text-[10px] font-medium justify-center shrink-0"
    >{{ displayCount }}</Badge>

    <!-- New button -->
    <button
      v-if="item.show_new_btn"
      class="opacity-0 group-hover:opacity-100 rounded p-0.5 text-muted-foreground hover:text-primary hover:bg-primary/10 transition-all shrink-0"
      title="Створити новий"
      @click="createNew"
    >
      <Plus class="size-3.5" />
    </button>
  </button>
</template>
