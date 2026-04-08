<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useWorkspaceStore } from '@/stores/workspace'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import NotificationsPopover from '@/components/layout/NotificationsPopover.vue'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  ArrowLeft,
  PanelLeftClose,
  PanelLeft,
  LogOut,
  ChevronsUpDown,
  Sun,
  Moon,
  Monitor,
  Settings2,
  Search,
  Shield,
  LayoutDashboard,
  Activity,
  Mail,
  X,
} from 'lucide-vue-next'
import { useColorMode } from '@/core/composables/useColorMode'
import type { Theme } from '@/core/composables/useColorMode'
import { Button } from '@/components/ui/button'
import SidebarItem from './SidebarItem.vue'
import SidebarEditor from './SidebarEditor.vue'

defineProps<{ workspaceName: string }>()

const wsStore = useWorkspaceStore()
const auth = useAuthStore()
const router = useRouter()

const collapsed = ref(false)
const showEditor = ref(false)
const recentDocs = ref<Array<{ workspace: string; doctype: string; id: string; title: string; ts: number }>>([])
const pinnedItems = ref<{ workspace: string; type: string; link_to: string; label: string; icon: string }[]>([])

const _onOpenQuickCreate = () => {
  window.dispatchEvent(new CustomEvent('toggle-search'))
  window.dispatchEvent(new CustomEvent('command-palette-open-quick-create'))
}

onMounted(() => {
  const saved = localStorage.getItem('grunt_sidebar_collapsed')
  if (saved === 'true') collapsed.value = true
  if (window.innerWidth >= 768 && window.innerWidth <= 1024) {
    collapsed.value = true
  }
  loadRecentDocs()
  loadPinnedItems()
  window.addEventListener('grunt_sidebar_pinned_changed', loadPinnedItems)
  window.addEventListener('grunt_recent_docs_changed', loadRecentDocs)
  window.addEventListener('open-quick-create', _onOpenQuickCreate)
})

onUnmounted(() => {
  window.removeEventListener('grunt_sidebar_pinned_changed', loadPinnedItems)
  window.removeEventListener('grunt_recent_docs_changed', loadRecentDocs)
  window.removeEventListener('open-quick-create', _onOpenQuickCreate)
})

watch(() => wsStore.active?.name, () => {
  loadRecentDocs()
  loadPinnedItems()
})

function toggleCollapse() {
  collapsed.value = !collapsed.value
  localStorage.setItem('grunt_sidebar_collapsed', String(collapsed.value))
}

function goToDesk() {
  router.push('/')
}

function initials(name: string): string {
  return name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
}

const mobileOpen = ref(false)
const colorMode = useColorMode()

async function onThemeChange(theme: string) {
  await auth.setTheme(theme as Theme)
}

function triggerSearch() {
  window.dispatchEvent(new CustomEvent('toggle-search'))
}

function loadRecentDocs() {
  try {
    const key = 'grunt_recent_docs'
    const saved = localStorage.getItem(key)
    if (!saved) {
      recentDocs.value = []
      return
    }
    const parsed = JSON.parse(saved) as Array<{ workspace: string; doctype: string; id: string; title: string; ts: number }>
    recentDocs.value = parsed
      .slice(0, 10)
      .map(r => ({ ...r }))
  } catch {
    recentDocs.value = []
  }
}

function getPinKey(workspace: string, type: string, link_to: string) {
  return `${workspace}:${type}:${link_to}`
}

function unpinItem(item: { workspace: string; type: string; link_to: string }) {
  try {
    const key = 'grunt_sidebar_pinned'
    const saved = localStorage.getItem(key)
    if (!saved) return
    const list = JSON.parse(saved) as string[]
    const idx = list.indexOf(getPinKey(item.workspace, item.type, item.link_to))
    if (idx >= 0) {
      list.splice(idx, 1)
      localStorage.setItem(key, JSON.stringify(list.slice(0, 20)))
      window.dispatchEvent(new Event('grunt_sidebar_pinned_changed'))
      loadPinnedItems()
    }
  } catch {
    // ignore
  }
}

function navigatePinnedItem(item: { workspace: string; type: string; link_to: string }) {
  switch (item.type) {
    case 'DocType':
      router.push(`/${item.workspace}/list/${item.link_to}`)
      break
    case 'Report':
      router.push(`/${item.workspace}/report/${item.link_to}`)
      break
    case 'Dashboard':
      router.push(`/${item.workspace}/dashboard/${item.link_to}`)
      break
    case 'URL':
      window.open(item.link_to, '_blank')
      break
    default:
      router.push(`/${item.workspace}/list/${item.link_to}`)
  }
}

function loadPinnedItems() {
  try {
    const key = 'grunt_sidebar_pinned'
    const saved = localStorage.getItem(key)
    if (!saved) {
      pinnedItems.value = []
      return
    }
    const ids = JSON.parse(saved) as string[]
    pinnedItems.value = ids
      .map((id) => {
        const [workspace, type, link_to] = id.split(':')
        if (!workspace || !type || !link_to) return null
        const found = wsStore.active?.items.find(i => i.type === type && i.link_to === link_to)
        const label = found?.label || link_to
        const icon = found?.icon || '📌'
        return { workspace, type, link_to, label, icon }
      })
      .filter((item): item is { workspace: string; type: string; link_to: string; label: string; icon: string } => !!item)
      .slice(0, 10)
  } catch {
    pinnedItems.value = []
  }
}


defineExpose({ mobileOpen })
</script>

<template>
  <!-- Mobile overlay -->
  <Transition name="overlay">
    <div v-if="mobileOpen" class="fixed inset-0 bg-black/40 backdrop-blur-sm z-40 md:hidden"
      @click="mobileOpen = false" />
  </Transition>

  <TooltipProvider :delay-duration="0">
    <aside class="flex flex-col bg-sidebar border-r border-sidebar-border h-screen transition-all duration-200 shrink-0"
      :class="[
        collapsed ? 'w-[52px]' : 'w-[240px]',
        mobileOpen ? 'fixed inset-y-0 left-0 z-50' : 'hidden md:flex'
      ]">
      <!-- Header -->
      <!-- Header / Workspace Switcher -->
      <div class="px-2 py-4 border-b border-sidebar-border bg-sidebar-background/50 backdrop-blur-md sticky top-0 z-10">
        <DropdownMenu v-if="!collapsed">
          <DropdownMenuTrigger as-child>
            <button
              class="group w-full flex items-center justify-between px-3 py-2.5 rounded-xl border border-sidebar-border/50 hover:border-primary/20 hover:bg-primary/5 transition-all duration-300 shadow-sm hover:shadow-md">
              <div class="flex items-center gap-3 min-w-0">
                <div
                  class="size-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0 group-hover:scale-105 transition-transform">
                  <span class="text-xl leading-none">{{ wsStore.active?.icon || '📁' }}</span>
                </div>
                <div class="flex flex-col items-start min-w-0">
                  <span class="text-[11px] font-bold text-primary/80 uppercase tracking-widest leading-none mb-1">
                    {{ wsStore.active?.name === 'grunt' ? 'СИСТЕМА' : 'РОБОЧИЙ ПРОСТІР' }}
                  </span>
                  <span class="text-sm font-semibold text-foreground truncate w-full">{{ wsStore.active?.label }}</span>
                </div>
              </div>
              <ChevronsUpDown
                class="size-4 text-muted-foreground/60 group-hover:text-primary/70 transition-colors shrink-0 ml-2" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" class="w-[200px] rounded-xl shadow-xl p-1.5 z-[100]">
            <DropdownMenuItem v-for="ws in wsStore.workspaces" :key="ws.name"
              class="flex items-center gap-2.5 px-3 py-2.5 rounded-lg cursor-pointer transition-colors"
              :class="ws.name === wsStore.active?.name ? 'bg-primary/5 text-primary font-medium' : ''"
              @click="router.push(`/${ws.name}`)">
              <span class="text-lg shrink-0">{{ ws.icon }}</span>
              <span class="text-sm truncate">{{ ws.label }}</span>
            </DropdownMenuItem>
            <DropdownMenuSeparator class="mx-1 my-1" />
            <DropdownMenuItem
              class="flex items-center gap-2.5 px-3 py-2.5 rounded-lg cursor-pointer hover:bg-destructive/5 hover:text-destructive transition-colors group"
              @click="goToDesk">
              <ArrowLeft class="size-4 text-muted-foreground/60 group-hover:text-destructive transition-colors" />
              <span class="text-sm">На головну</span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <Tooltip v-else :delay-duration="0">
          <TooltipTrigger as-child>
            <button
              class="mx-auto size-9 rounded-lg bg-primary/5 border border-sidebar-border/50 flex items-center justify-center hover:bg-primary/10 transition-colors"
              @click="goToDesk">
              <span class="text-lg">{{ wsStore.active?.icon || '📁' }}</span>
            </button>
          </TooltipTrigger>
          <TooltipContent side="right">
            {{ wsStore.active?.label }}
          </TooltipContent>
        </Tooltip>
      </div>

      <!-- Search Trigger -->
      <div class="px-3 py-2">
        <button
          class="w-full flex items-center justify-between px-3 py-2 rounded-lg border border-sidebar-border/30 bg-muted/30 hover:bg-muted/50 hover:border-primary/20 transition-all group shadow-sm"
          @click="triggerSearch">
          <div class="flex items-center gap-2.5 min-w-0">
            <Search class="size-4 text-muted-foreground group-hover:text-primary transition-colors shrink-0" />
            <span v-if="!collapsed"
              class="text-xs font-medium text-muted-foreground group-hover:text-foreground transition-colors">Пошук...</span>
          </div>
          <div v-if="!collapsed"
            class="flex items-center gap-0.5 px-1.5 py-0.5 rounded border border-sidebar-border/50 bg-background text-[9px] font-bold text-muted-foreground shadow-sm group-hover:border-primary/20 transition-all">
            <span class="opacity-70 text-[10px]">⌘</span>
            <span>K</span>
          </div>
        </button>
      </div>

      <!-- Notifications -->
      <div v-if="!collapsed" class="px-3 mb-2">
        <NotificationsPopover :workspace="wsStore.active?.name" />
      </div>


      <!-- Pinned items -->
      <div v-if="!collapsed && pinnedItems.length" class="px-3 mb-2">
        <div class="text-[11px] tracking-widest font-bold uppercase text-muted-foreground mb-1">Закріплені</div>
        <div class="space-y-1">
          <div v-for="item in pinnedItems" :key="`${item.workspace}-${item.type}-${item.link_to}`"
            class="w-full flex items-center justify-between text-sm px-2 py-1 rounded hover:bg-accent/70 transition">
            <button class="text-left flex-1 truncate" @click="navigatePinnedItem(item)">
              {{ item.icon }} {{ item.label }}
              <span class="text-[10px] text-muted-foreground lowercase ml-1">({{ item.type }})</span>
            </button>
            <button class="ml-2 rounded-md p-1 text-muted-foreground/60 hover:text-destructive hover:bg-destructive/10"
              title="Відкріпити" @click.stop="unpinItem(item)">
              <X class="size-3" />
            </button>
          </div>
        </div>
      </div>

      <!-- Navigation -->
      <ScrollArea class="flex-1">
        <nav class="p-2 flex flex-col gap-0.5">
          <!-- Workspace Dashboard — always shown at top of navigation -->
          <RouterLink :to="`/${workspaceName}/dashboard/${workspaceName}`" custom v-slot="{ isActive, href, navigate }">
            <a :href="href" @click="navigate"
              class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all"
              :class="isActive ? 'bg-primary/5 text-primary font-medium' : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground'">
              <LayoutDashboard class="w-4 h-4 shrink-0"
                :class="isActive ? 'text-primary' : 'text-muted-foreground/70'" />
              <span v-if="!collapsed" class="truncate font-medium">Огляд</span>
            </a>
          </RouterLink>
          <Separator class="my-2" />

          <template v-for="(group, gi) in wsStore.groupedItems" :key="gi">
            <!-- Divider -->
            <Separator v-if="group.section === '__divider__'" class="my-2" />

            <template v-else>
              <!-- Section label -->
              <p v-if="group.section && !collapsed"
                class="px-2.5 pt-4 pb-1 text-[11px] font-bold uppercase tracking-wider text-muted-foreground select-none">
                {{ group.section }}</p>

              <SidebarItem v-for="item in group.items" :key="item.link_to + item.sequence" :item="item"
                :workspace-name="workspaceName"
                :count="wsStore.counts[item.link_to] ?? wsStore.counts[item.link_to + '_' + (item.count_filters ? Object.values(JSON.parse(item.count_filters || '{}')).join('_').toLowerCase() : '')] ?? 0"
                :collapsed="collapsed" :color="wsStore.active?.color" />
            </template>
          </template>

          <div v-if="!collapsed && auth.user?.is_superadmin" class="px-2 pt-6 space-y-1">
            <!-- Quick admin shortcuts → all point to standard DocType ListViews -->
            <RouterLink :to="`/grunt/list/DocTypePermission`" custom v-slot="{ isActive, href, navigate }">
              <a :href="href" @click="navigate"
                class="flex items-center gap-2 px-3 h-8 rounded-lg text-xs font-bold uppercase tracking-wider transition-all border"
                :class="isActive ? 'bg-primary/10 text-primary border-primary/20' : 'text-muted-foreground/70 border-dashed border-border/70 hover:text-primary hover:bg-primary/5 hover:border-primary/20'">
                <Shield class="size-3.5" />
                Права доступу
              </a>
            </RouterLink>
            <RouterLink :to="`/grunt/list/ActivityLog`" custom v-slot="{ isActive, href, navigate }">
              <a :href="href" @click="navigate"
                class="flex items-center gap-2 px-3 h-8 rounded-lg text-xs font-bold uppercase tracking-wider transition-all border"
                :class="isActive ? 'bg-primary/10 text-primary border-primary/20' : 'text-muted-foreground/70 border-dashed border-border/70 hover:text-primary hover:bg-primary/5 hover:border-primary/20'">
                <Activity class="size-3.5" />
                Журнал активності
              </a>
            </RouterLink>
            <RouterLink :to="`/grunt/list/EmailAccount`" custom v-slot="{ isActive, href, navigate }">
              <a :href="href" @click="navigate"
                class="flex items-center gap-2 px-3 h-8 rounded-lg text-xs font-bold uppercase tracking-wider transition-all border"
                :class="isActive ? 'bg-primary/10 text-primary border-primary/20' : 'text-muted-foreground/70 border-dashed border-border/70 hover:text-primary hover:bg-primary/5 hover:border-primary/20'">
                <Mail class="size-3.5" />
                Пошта
              </a>
            </RouterLink>
            <Button variant="ghost" size="sm"
              class="w-full justify-start text-[11px] font-bold text-muted-foreground/70 hover:text-primary hover:bg-primary/5 hover:border-primary/20 border border-dashed border-border/70 h-8 uppercase tracking-wider"
              @click="showEditor = true">
              <Settings2 class="size-3.5 mr-2" />
              Налаштувати
            </Button>
          </div>
        </nav>
      </ScrollArea>

      <SidebarEditor v-if="wsStore.active" v-model:open="showEditor" :workspace="wsStore.active"
        @saved="wsStore.setActive(workspaceName)" />

      <!-- Footer -->
      <div class="border-t border-sidebar-border shrink-0 p-2">
        <!-- Collapse toggle (desktop only) -->
        <button
          class="w-full flex items-center justify-center p-1.5 rounded-md text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors mb-1 hidden md:flex"
          :title="collapsed ? 'Розгорнути' : 'Згорнути'" @click="toggleCollapse">
          <PanelLeft v-if="collapsed" class="size-4" />
          <PanelLeftClose v-else class="size-4" />
        </button>

        <!-- User menu -->
        <DropdownMenu v-if="!collapsed">
          <DropdownMenuTrigger as-child>
            <button class="w-full flex items-center gap-2 p-1.5 rounded-md hover:bg-accent transition-colors">
              <span
                class="size-7 rounded-md bg-primary text-primary-foreground text-xs font-medium flex items-center justify-center shrink-0">
                {{ auth.user ? initials(auth.user.full_name) : '?' }}
              </span>
              <div class="flex-1 text-left min-w-0">
                <p class="text-sm font-medium text-foreground truncate leading-tight">{{ auth.user?.full_name }}</p>
                <p class="text-[11px] text-muted-foreground truncate leading-tight">{{ auth.user?.email }}</p>
              </div>
              <ChevronsUpDown class="size-4 text-muted-foreground shrink-0" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent side="top" align="start" class="w-56">
            <DropdownMenuLabel class="text-xs text-muted-foreground font-normal">Тема</DropdownMenuLabel>
            <DropdownMenuRadioGroup :model-value="colorMode.currentTheme.value"
              @update:model-value="(v) => typeof v === 'string' && onThemeChange(v)">
              <DropdownMenuRadioItem value="light">
                <Sun class="size-3.5 mr-2" />
                Світла
              </DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="dark">
                <Moon class="size-3.5 mr-2" />
                Темна
              </DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="system">
                <Monitor class="size-3.5 mr-2" />
                Системна
              </DropdownMenuRadioItem>
            </DropdownMenuRadioGroup>
            <DropdownMenuSeparator />
            <DropdownMenuItem @click="auth.logout?.()">
              <LogOut class="size-4 mr-2" />
              Вийти
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <!-- Collapsed: avatar only -->
        <Tooltip v-else>
          <TooltipTrigger as-child>
            <button class="w-full flex items-center justify-center p-1.5 rounded-md hover:bg-accent transition-colors">
              <span
                class="size-7 rounded-md bg-primary text-primary-foreground text-xs font-medium flex items-center justify-center">
                {{ auth.user ? initials(auth.user.full_name) : '?' }}
              </span>
            </button>
          </TooltipTrigger>
          <TooltipContent side="right">{{ auth.user?.full_name }}</TooltipContent>
        </Tooltip>
      </div>
    </aside>
  </TooltipProvider>
</template>

<style scoped>
.overlay-enter-active,
.overlay-leave-active {
  transition: opacity 200ms ease;
}

.overlay-enter-from,
.overlay-leave-to {
  opacity: 0;
}
</style>
