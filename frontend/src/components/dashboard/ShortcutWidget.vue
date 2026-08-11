<script setup lang="ts">
import { computed } from 'vue'
import type { DashboardWidget } from '@/types'
import * as LucideIcons from '@lucide/vue'
import { ExternalLink } from '@lucide/vue'
import { useRouter } from 'vue-router'

const props = defineProps<{
  widget: DashboardWidget
  data: { count: number } | null
  loading?: boolean
  workspaceName?: string
}>()

const router = useRouter()

const iconComponent = computed(() => {
  if (!props.widget.icon) return ExternalLink
  return (LucideIcons as Record<string, unknown>)[props.widget.icon] as typeof ExternalLink ?? ExternalLink
})

const colorMap: Record<string, string> = {
  primary: 'bg-primary/10 text-primary',
  blue: 'bg-blue-500/10 text-blue-600',
  amber: 'bg-amber-500/10 text-amber-600',
  red: 'bg-red-500/10 text-red-600',
  violet: 'bg-violet-500/10 text-violet-600',
  cyan: 'bg-cyan-500/10 text-cyan-600',
}

const iconBg = computed(() => colorMap[props.widget.color] ?? colorMap.primary)

function navigate() {
  const linkType = props.widget.link_type ?? 'DocType'
  const target = props.widget.doctype ?? ''
  const ws = props.workspaceName ?? ''
  if (linkType === 'URL') {
    window.open(target, '_blank')
  } else if (linkType === 'Report') {
    router.push({ name: 'workspace-report', params: { workspaceName: ws, reportName: target } })
  } else if (linkType === 'Page') {
    router.push({ name: 'workspace-page', params: { workspaceName: ws, pageName: target } })
  } else {
    router.push(`/${ws}/${target}`)
  }
}
</script>

<template>
  <button
    class="flex flex-col gap-3 p-5 h-full w-full text-left hover:bg-muted/40 transition-colors"
    @click="navigate">
    <div class="flex items-center justify-between w-full">
      <div :class="['p-2 rounded-lg', iconBg]">
        <component :is="iconComponent" class="w-4 h-4" />
      </div>
      <span v-if="data?.count != null"
        class="text-xs font-semibold px-2 py-0.5 rounded-full bg-muted text-muted-foreground tabular-nums">
        {{ data.count }}
      </span>
    </div>
    <div class="flex flex-col gap-0.5">
      <span class="font-semibold text-sm text-foreground">{{ widget.title }}</span>
      <span v-if="widget.description" class="text-xs text-muted-foreground line-clamp-2">
        {{ widget.description }}
      </span>
    </div>
  </button>
</template>
