<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import type { WorkspaceLink } from '@/core/api/workspace'
import { Plus, Star, StarOff } from '@lucide/vue'
import {
  SidebarMenuItem,
  SidebarMenuButton,
} from '@/components/ui/sidebar'
import AppIcon from '@/components/AppIcon.vue'

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
    <SidebarMenuButton :is-active="isActive" @click="navigate">
      <AppIcon :icon="item.icon || 'file'" class="size-4 shrink-0" />
      <span class="flex-1 truncate">{{ item.label }}</span>
      <!-- Hover actions: pin + new (hidden when collapsed) -->
      <div
        class="ml-auto flex items-center gap-0.5 opacity-0 group-hover/menu-item:opacity-100 group-data-[collapsible=icon]:hidden transition-opacity pointer-events-none group-hover/menu-item:pointer-events-auto">
        <button
          class="flex size-6 items-center justify-center rounded-md hover:bg-sidebar-accent text-sidebar-foreground/50 hover:text-sidebar-foreground transition-colors"
          :title="pinned ? 'Відкріпити' : 'Закріпити'"
          @click.stop="togglePin">
          <component :is="pinned ? Star : StarOff" class="size-3.5" :class="pinned ? 'fill-current text-primary' : ''" />
        </button>
        <button v-if="item.show_new_btn"
          class="flex size-6 items-center justify-center rounded-md hover:bg-sidebar-accent text-sidebar-foreground/50 hover:text-sidebar-foreground transition-colors"
          title="Створити новий"
          @click.stop="createNew">
          <Plus class="size-3.5" />
        </button>
      </div>

      <Badge v-if="displayCount"
        :value="displayCount"
        severity="secondary"
        style="font-size: 10px; padding: 0 6px; height: 18px; min-width: 18px;"
        class="ml-2 rounded-full tabular-nums"
      />
    </SidebarMenuButton>
  </SidebarMenuItem>
</template>
