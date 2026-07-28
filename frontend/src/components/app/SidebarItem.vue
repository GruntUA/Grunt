<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import type { WorkspaceLink } from '@/core/api/workspace'
import { Plus, Star, StarOff } from '@lucide/vue'
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

    <SidebarMenuAction show-on-hover :title="pinned ? 'Відкріпити' : 'Закріпити'" @click.stop="togglePin">
      <component :is="pinned ? Star : StarOff" :class="pinned ? 'fill-current text-primary' : ''" />
    </SidebarMenuAction>
    <SidebarMenuAction v-if="item.show_new_btn" show-on-hover class="right-7" title="Створити новий" @click.stop="createNew">
      <Plus />
    </SidebarMenuAction>
  </SidebarMenuItem>
</template>
