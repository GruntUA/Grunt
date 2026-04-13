<script setup lang="ts">
import { computed, ref, shallowRef, onMounted, onUnmounted } from 'vue'
import type { Component } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import type { WorkspaceLink } from '@/core/api/workspace'
import { Badge } from '@/components/ui/badge'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { Plus, Star, StarOff } from 'lucide-vue-next'

// ── Lucide icon resolution ────────────────────────────────────────────────────
type IconMap = Record<string, Component>
const lucideIcons = shallowRef<IconMap>({})
let lucideLoaded = false

function loadLucide() {
  if (lucideLoaded) return
  lucideLoaded = true
  import('lucide-vue-next').then(lib => { lucideIcons.value = lib as unknown as IconMap })
}

/** Returns the Lucide component for a kebab-case name, or null if not lucide. */
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
  if (props.item.type === 'Dashboard') {
    return route.params.dashboardName === props.item.link_to
  }
  return false
})

function navigate() {
  switch (props.item.type) {
    case 'DocType':
      if (props.item.is_singleton) {
        router.push(`/${props.workspaceName}/list/${props.item.link_to}/${props.item.link_to}`)
      } else {
        router.push(`/${props.workspaceName}/list/${props.item.link_to}`)
      }
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

function getPinKey(): string {
  return `${props.workspaceName}:${props.item.type}:${props.item.link_to}`
}

const pinUpdateSignal = ref(0)

const pinned = computed(() => {
  pinUpdateSignal.value
  try {
    const list = JSON.parse(localStorage.getItem('grunt_sidebar_pinned') || '[]') as string[]
    return list.includes(getPinKey())
  } catch {
    return false
  }
})

function syncPinned() {
  pinUpdateSignal.value++
}

onMounted(() => {
  window.addEventListener('grunt_sidebar_pinned_changed', syncPinned)
})

onUnmounted(() => {
  window.removeEventListener('grunt_sidebar_pinned_changed', syncPinned)
})

function togglePin(e: Event) {
  e.stopPropagation()
  try {
    const key = getPinKey()
    const list = JSON.parse(localStorage.getItem('grunt_sidebar_pinned') || '[]') as string[]
    const idx = list.indexOf(key)
    if (idx >= 0) {
      list.splice(idx, 1)
    } else {
      list.unshift(key)
    }
    localStorage.setItem('grunt_sidebar_pinned', JSON.stringify(list.slice(0, 20)))
    window.dispatchEvent(new Event('grunt_sidebar_pinned_changed'))
    syncPinned()
  } catch {
    // ignore
  }
}

const displayCount = computed(() => {
  if (!props.count || props.count <= 0) return ''
  return props.count > 99 ? '99+' : String(props.count)
})
</script>

<template>
  <Tooltip v-if="collapsed" :delay-duration="0">
    <TooltipTrigger as-child>
      <button class="w-full flex items-center justify-center h-9 rounded-md transition-colors" :class="isActive
        ? 'bg-primary/10 text-primary'
        : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'" @click="navigate">
        <component :is="getLucideIcon(item.icon)" v-if="getLucideIcon(item.icon)" class="size-4" />
        <span v-else class="text-sm">{{ item.icon || '📄' }}</span>
      </button>
    </TooltipTrigger>
    <TooltipContent side="right" :side-offset="8">
      {{ item.label }}
      <span v-if="displayCount" class="ml-1 text-muted-foreground">({{ displayCount }})</span>
    </TooltipContent>
  </Tooltip>

  <div v-else role="button" tabindex="0"
    class="group w-full flex items-center gap-3 px-3 h-10 rounded-xl text-left transition-all duration-300 relative mb-1 cursor-pointer overflow-hidden border border-transparent"
    :class="isActive
      ? 'bg-primary/10 text-primary font-bold shadow-sm border-primary/20'
      : 'text-muted-foreground/80 hover:bg-accent/50 hover:text-foreground hover:border-accent-foreground/5'" @click="navigate"
    @keydown.enter.prevent="navigate" @keydown.space.prevent="navigate">
    
    <!-- Hover/Active Glow -->
    <div v-if="isActive" class="absolute inset-0 bg-gradient-to-r from-primary/5 to-transparent pointer-events-none" />
    <div class="absolute inset-y-2 left-0 w-1 bg-primary rounded-r-full transition-all duration-300 transform"
      :class="isActive ? 'scale-y-100 opacity-100' : 'scale-y-0 opacity-0 group-hover:scale-y-50 group-hover:opacity-50'" />

    <span class="text-base shrink-0 w-5 flex items-center justify-center transition-all duration-300 group-hover:scale-125 group-hover:rotate-6"
      :class="isActive ? 'text-primary drop-shadow-sm' : 'text-muted-foreground/70'">
      <component :is="getLucideIcon(item.icon)" v-if="getLucideIcon(item.icon)" class="size-4" />
      <template v-else>{{ item.icon || '📄' }}</template>
    </span>
    <span class="text-[13px] truncate flex-1 tracking-tight font-semibold relative z-10">{{ item.label }}</span>

    <!-- Count badge -->
    <Badge v-if="displayCount" variant="secondary"
      class="h-5 min-w-5 px-1.5 text-[10px] font-black justify-center shrink-0 bg-primary/10 text-primary border-none rounded-lg shadow-inner">
      {{ displayCount }}</Badge>

    <!-- Actions Container -->
    <div class="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
      <!-- Pin toggle -->
      <button
        class="rounded-lg p-1.5 text-muted-foreground/40 hover:text-primary hover:bg-primary/10 transition-all shrink-0"
        :title="pinned ? 'Відкріпити' : 'Закріпити'" @click.stop="togglePin">
        <component :is="pinned ? Star : StarOff" class="size-3.5" :class="pinned ? 'fill-primary text-primary opacity-100' : ''" />
      </button>

      <!-- New button -->
      <button v-if="item.show_new_btn"
        class="rounded-lg p-1.5 text-muted-foreground/40 hover:text-primary hover:bg-primary/10 transition-all shrink-0"
        title="Створити новий" @click.stop="createNew">
        <Plus class="size-3.5" />
      </button>
    </div>
  </div>

</template>
