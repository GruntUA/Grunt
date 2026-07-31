<script setup lang="ts">
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import type { WorkspaceLink } from '@/core/api/workspace'
import { Plus } from '@lucide/vue'
import AppIcon from '@/components/AppIcon.vue'
import { cn } from '@/lib/utils'

const props = defineProps<{
  item: WorkspaceLink
  workspaceName: string
  count?: number
  color?: string
  /** Render as a SidebarMenuSubItem (nested inside a Collapsible group) instead of a top-level SidebarMenuItem. */
  nested?: boolean
}>()

/** Hover-reveal icon button classes shared by pin/create actions in nested mode (SidebarMenuAction's own classes assume a top-level `group/menu-item`, which SidebarMenuSubItem doesn't provide). */
const nestedActionClass = 'text-sidebar-foreground ring-sidebar-ring hover:bg-sidebar-accent hover:text-sidebar-accent-foreground absolute top-1/2 -translate-y-1/2 flex aspect-square w-5 items-center justify-center rounded-md p-0 outline-hidden transition-transform focus-visible:ring-2 [&>svg]:size-4 [&>svg]:shrink-0 opacity-0 group-hover/menu-sub-item:opacity-100 group-focus-within/menu-sub-item:opacity-100 md:opacity-0'

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

function createNew(e: Event) {
  e.stopPropagation()
  router.push(`/${props.workspaceName}/${props.item.link_to}/new`)
}

const displayCount = computed(() => {
  if (!props.count || props.count <= 0) return ''
  return props.count > 99 ? '99+' : String(props.count)
})
</script>

<template>
  <SidebarMenuSubItem v-if="nested">
    <SidebarMenuSubButton as-child :is-active="isActive">
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

    <span v-if="displayCount" class="text-sidebar-foreground pointer-events-none absolute top-1/2 right-1 flex h-5 min-w-5 -translate-y-1/2 items-center justify-center rounded-md px-1 text-xs font-medium tabular-nums select-none">
      {{ displayCount }}
    </span>

    <button v-if="item.show_new_btn" type="button" :class="cn(nestedActionClass, 'right-7')" title="Створити новий" @click.stop="createNew">
      <Plus />
    </button>
  </SidebarMenuSubItem>

  <SidebarMenuItem v-else>
    <SidebarMenuButton as-child :is-active="isActive" :tooltip="item.label">
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

    <SidebarMenuBadge v-if="displayCount">{{ displayCount }}</SidebarMenuBadge>

    <SidebarMenuAction v-if="item.show_new_btn" show-on-hover class="right-7" title="Створити новий" @click.stop="createNew">
      <Plus />
    </SidebarMenuAction>
  </SidebarMenuItem>
</template>
