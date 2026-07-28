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
  collapsed?: boolean
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
  <li class="relative list-none group/item">
    <a
      :href="itemHref"
      class="w-full flex items-center gap-2.5 px-2 py-2.5 rounded-xl transition-all duration-300 group relative overflow-hidden"
      :class="[
        isActive
          ? 'bg-primary/10 text-primary font-bold shadow-sm'
          : 'text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground',
        collapsed ? 'justify-center px-1' : ''
      ]"
      :target="item.type === 'URL' ? '_blank' : undefined"
      :rel="item.type === 'URL' ? 'noopener noreferrer' : undefined"
      @click="navigate"
    >
      <AppIcon :icon="item.icon || 'file'" class="size-4 shrink-0 transition-all duration-300 group-hover:scale-110 group-hover:rotate-3" />

      <template v-if="!collapsed">
        <span class="flex-1 truncate text-[13px] text-left leading-none">{{ item.label }}</span>

        <!-- Hover actions -->
        <div class="flex items-center gap-1 opacity-0 group-hover/item:opacity-100 transition-all duration-300">
          <button
            class="flex size-7 items-center justify-center rounded-lg hover:bg-primary/20 text-muted-foreground/50 hover:text-primary transition-all"
            @click.stop="togglePin"
          >
            <component :is="pinned ? Star : StarOff" class="size-3.5" :class="pinned ? 'fill-current text-primary' : ''" />
          </button>
          <button
            v-if="item.show_new_btn"
            class="flex size-7 items-center justify-center rounded-lg hover:bg-primary/20 text-muted-foreground/50 hover:text-primary transition-all"
            @click.stop="createNew"
          >
            <Plus class="size-4" />
          </button>
        </div>

        <Badge v-if="displayCount"
          variant="secondary"
          class="ml-2 !text-[10px] !h-4.5 !min-w-4.5 !px-1.5 !font-bold !rounded-full !shadow-inner"
        >{{ displayCount }}</Badge>
      </template>

      <!-- Indicator line for active state -->
      <div v-if="isActive" class="absolute left-0 top-1/4 bottom-1/4 w-1 bg-primary rounded-r-full" />
    </a>
  </li>
</template>
