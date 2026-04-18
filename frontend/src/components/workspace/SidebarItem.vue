<script setup lang="ts">
import { computed, ref, shallowRef, onMounted, onUnmounted } from 'vue'
import type { Component } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import type { WorkspaceLink } from '@/core/api/workspace'
import { Plus, Star, StarOff } from '@lucide/vue'
import {
  SidebarMenuItem,
  SidebarMenuButton,
  SidebarMenuBadge,
} from '@/components/ui/sidebar'

// ── Lucide icon resolution ────────────────────────────────────────────────────
type IconMap = Record<string, Component>
const lucideIcons = shallowRef<IconMap>({})
let lucideLoaded = false

function loadLucide() {
  if (lucideLoaded) return
  lucideLoaded = true
  import('@lucide/vue').then(lib => { lucideIcons.value = lib as unknown as IconMap })
}

function getLucideIcon(icon: string | undefined): Component | null {
  if (!icon || !/^[a-z][a-z0-9-]+$/.test(icon)) return null
  loadLucide()
  const pascal = icon.split('-').map(s => s.charAt(0).toUpperCase() + s.slice(1)).join('')
  return (lucideIcons.value[pascal] as Component) ?? null
}

const props = defineProps<{
  item: WorkspaceLink
  workspaceName: string
  count?: number
  color?: string
}>()

const router = useRouter()
const route = useRoute()

const isActive = computed(() => {
  if (props.item.type === 'DocType') return route.params.doctype === props.item.link_to
  if (props.item.type === 'Report') return route.params.reportName === props.item.link_to
  if (props.item.type === 'Dashboard') return route.params.dashboardName === props.item.link_to
  return false
})

function navigate() {
  switch (props.item.type) {
    case 'DocType':
      router.push(props.item.is_singleton
        ? `/${props.workspaceName}/list/${props.item.link_to}/${props.item.link_to}`
        : `/${props.workspaceName}/list/${props.item.link_to}`)
      break
    case 'Report': router.push(`/${props.workspaceName}/report/${props.item.link_to}`); break
    case 'URL': window.open(props.item.link_to, '_blank'); break
    case 'Dashboard': router.push(`/${props.workspaceName}/dashboard/${props.item.link_to}`); break
  }
}

function createNew(e: Event) {
  e.stopPropagation()
  router.push(`/${props.workspaceName}/list/${props.item.link_to}/new`)
}

function getPinKey(): string {
  return `${props.workspaceName}:${props.item.type}:${props.item.link_to}`
}

const pinUpdateSignal = ref(0)

const pinned = computed(() => {
  pinUpdateSignal.value
  try {
    const list = JSON.parse(localStorage.getItem('grunt_sidebar_pinned') || '[]') as string[]
    return list.includes(getPinKey())
  } catch { return false }
})

function syncPinned() { pinUpdateSignal.value++ }

onMounted(() => window.addEventListener('grunt_sidebar_pinned_changed', syncPinned))
onUnmounted(() => window.removeEventListener('grunt_sidebar_pinned_changed', syncPinned))

function togglePin(e: Event) {
  e.stopPropagation()
  try {
    const key = getPinKey()
    const list = JSON.parse(localStorage.getItem('grunt_sidebar_pinned') || '[]') as string[]
    const idx = list.indexOf(key)
    if (idx >= 0) list.splice(idx, 1)
    else list.unshift(key)
    localStorage.setItem('grunt_sidebar_pinned', JSON.stringify(list.slice(0, 20)))
    window.dispatchEvent(new Event('grunt_sidebar_pinned_changed'))
    syncPinned()
  } catch { /* ignore */ }
}

const displayCount = computed(() => {
  if (!props.count || props.count <= 0) return ''
  return props.count > 99 ? '99+' : String(props.count)
})
</script>

<template>
  <SidebarMenuItem>
    <SidebarMenuButton :is-active="isActive" :tooltip="item.label" @click="navigate">
      <component :is="getLucideIcon(item.icon)" v-if="getLucideIcon(item.icon)" class="shrink-0" />
      <span v-else class="text-base shrink-0 w-4 flex items-center justify-center">{{ item.icon || '📄' }}</span>
      <span class="flex-1 truncate">{{ item.label }}</span>
      <!-- Count badge - fades on hover to make room for actions -->
      <span v-if="displayCount"
        class="ml-auto text-[10px] font-black tabular-nums shrink-0 transition-opacity group-hover/menu-item:opacity-0">
        {{ displayCount }}
      </span>
    </SidebarMenuButton>

    <!-- Hover actions: pin + new (hidden when collapsed) -->
    <div
      class="absolute right-1 top-1/2 -translate-y-1/2 flex gap-0.5 opacity-0 group-hover/menu-item:opacity-100 group-data-[collapsible=icon]:hidden transition-opacity pointer-events-none group-hover/menu-item:pointer-events-auto">
      <button
        class="flex size-5 items-center justify-center rounded hover:bg-sidebar-accent text-sidebar-foreground/50 hover:text-sidebar-foreground transition-colors"
        :title="pinned ? 'Відкріпити' : 'Закріпити'"
        @click.stop="togglePin">
        <component :is="pinned ? Star : StarOff" class="size-3" :class="pinned ? 'fill-current text-primary' : ''" />
      </button>
      <button v-if="item.show_new_btn"
        class="flex size-5 items-center justify-center rounded hover:bg-sidebar-accent text-sidebar-foreground/50 hover:text-sidebar-foreground transition-colors"
        title="Створити новий"
        @click.stop="createNew">
        <Plus class="size-3" />
      </button>
    </div>
  </SidebarMenuItem>
</template>
