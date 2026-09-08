<script setup lang="ts">
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import type { WorkspaceLink } from '@/core/api/workspace'
import AppIcon from '@/components/AppIcon.vue'
import { SidebarMenuBadge, SidebarMenuButton, SidebarMenuItem, SidebarMenuSubButton, SidebarMenuSubItem } from '@/components/ui/sidebar'

const props = defineProps<{
  item: WorkspaceLink
  workspaceName: string
  count?: number
  color?: string
  /** Render as a SidebarMenuSubItem (nested inside a Collapsible group) instead of a top-level SidebarMenuItem. */
  nested?: boolean
}>()

const router = useRouter()
const route = useRoute()

const isActive = computed(() => {
  if (props.item.type === 'DocType') return route.params.doctype === props.item.link_to
  if (props.item.type === 'Report') return route.params.reportName === props.item.link_to
  if (props.item.type === 'Page') return route.params.pageName === props.item.link_to
  return false
})

function getRoutePath(): string | null {
  switch (props.item.type) {
    case 'DocType':
      return props.item.is_singleton
        ? `/${props.workspaceName}/${props.item.link_to}/${props.item.link_to}`
        : `/${props.workspaceName}/${props.item.link_to}`
    case 'Report': return `/${props.workspaceName}/report/${props.item.link_to}`
    case 'Page': return `/${props.workspaceName}/page/${props.item.link_to}`
    default: return null
  }
}

const itemHref = computed(() => {
  if (props.item.type === 'URL') return props.item.link_to
  return getRoutePath() ?? '#'
})

function navigate(e: MouseEvent) {
  // Let middle-click and Ctrl/Meta+click fall through to default <a> behavior
  if (e.button === 1 || e.ctrlKey || e.metaKey || e.shiftKey) return
  e.preventDefault()
  if (props.item.type === 'URL') { window.open(props.item.link_to, '_blank'); return }
  const path = getRoutePath()
  if (path) router.push(path)
}

const displayCount = computed(() => {
  const n = props.count ?? 0
  if (n <= 0) return ''
  // Show the real grouped number below 100k, then compact it: 123 456 → "123K", 1 200 000 → "1.2M".
  if (n < 100_000) return n.toLocaleString()
  if (n < 1_000_000) return `${Math.round(n / 1000)}K`
  return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, '')}M`
})
</script>

<template>
  <SidebarMenuSubItem v-if="nested">
    <SidebarMenuSubButton as-child :is-active="isActive" :class="displayCount ? 'pr-14' : undefined">
      <a
        :href="itemHref"
        :target="item.type === 'URL' ? '_blank' : undefined"
        :rel="item.type === 'URL' ? 'noopener noreferrer' : undefined"
        @click="navigate"
      >
        <AppIcon :icon="item.icon || 'file'" />
        <span>{{ item.label }}</span>
      </a>
    </SidebarMenuSubButton>

    <span
      v-if="displayCount"
      class="text-sidebar-foreground pointer-events-none absolute top-1/2 right-1 flex h-5 min-w-5 -translate-y-1/2 items-center justify-center rounded-md px-1 text-sm tabular-nums select-none group-data-[collapsible=icon]:hidden"
    >
      {{ displayCount }}
    </span>
  </SidebarMenuSubItem>

  <SidebarMenuItem v-else>
    <SidebarMenuButton as-child :is-active="isActive" :tooltip="item.label" :class="displayCount ? 'pr-14' : undefined">
      <a
        :href="itemHref"
        :target="item.type === 'URL' ? '_blank' : undefined"
        :rel="item.type === 'URL' ? 'noopener noreferrer' : undefined"
        @click="navigate"
      >
        <AppIcon :icon="item.icon || 'file'" />
        <span>{{ item.label }}</span>
      </a>
    </SidebarMenuButton>

    <SidebarMenuBadge v-if="displayCount" class="text-sm font-normal">{{ displayCount }}</SidebarMenuBadge>
  </SidebarMenuItem>
</template>
