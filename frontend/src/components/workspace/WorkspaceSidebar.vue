<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useWorkspaceStore } from '@/stores/workspace'
import { Separator } from '@/components/ui/separator'
import NotificationsPopover from '@/components/layout/NotificationsPopover.vue'
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
  LogOut,
} from '@lucide/vue'
import { useColorMode } from '@/core/composables/useColorMode'
import type { Theme } from '@/core/composables/useColorMode'
import { Button } from '@/components/ui/button'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  SidebarSeparator,
  useSidebar,
} from '@/components/ui/sidebar'
import SidebarItem from './SidebarItem.vue'
import SidebarEditor from './SidebarEditor.vue'

defineProps<{ workspaceName: string }>()

const wsStore = useWorkspaceStore()
const auth = useAuthStore()
const router = useRouter()
const colorMode = useColorMode()
const { state } = useSidebar()

const showEditor = ref(false)
const recentDocs = ref<Array<{ workspace: string; doctype: string; id: string; title: string; ts: number }>>([])
const pinnedItems = ref<{ workspace: string; type: string; link_to: string; label: string; icon: string }[]>([])

const _onOpenQuickCreate = () => {
  window.dispatchEvent(new CustomEvent('toggle-search'))
  window.dispatchEvent(new CustomEvent('command-palette-open-quick-create'))
}

onMounted(() => {
  loadRecentDocs()
  loadPinnedItems()
  window.addEventListener('grunt_sidebar_pinned_changed', loadPinnedItems)
  window.addEventListener('grunt_recent_docs_changed', () => {
    loadRecentDocs()
    wsStore.refreshCounts()
  })
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

watch(() => router.currentRoute.value.path, () => {
  if (wsStore.active) wsStore.refreshCounts()
})

function goToDesk() { router.push('/') }

function initials(name: string): string {
  return name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
}

function triggerSearch() {
  window.dispatchEvent(new CustomEvent('toggle-search'))
}

async function onThemeChange(theme: string) {
  await auth.setTheme(theme as Theme)
}

async function handleLogout() {
  await auth.logout()
  router.push('/login')
}

function loadRecentDocs() {
  try {
    const saved = localStorage.getItem('grunt_recent_docs')
    if (!saved) { recentDocs.value = []; return }
    recentDocs.value = (JSON.parse(saved) as typeof recentDocs.value).slice(0, 10)
  } catch { recentDocs.value = [] }
}

function getPinKey(workspace: string, type: string, link_to: string) {
  return `${workspace}:${type}:${link_to}`
}

function unpinItem(item: { workspace: string; type: string; link_to: string }) {
  try {
    const saved = localStorage.getItem('grunt_sidebar_pinned')
    if (!saved) return
    const list = JSON.parse(saved) as string[]
    const idx = list.indexOf(getPinKey(item.workspace, item.type, item.link_to))
    if (idx >= 0) {
      list.splice(idx, 1)
      localStorage.setItem('grunt_sidebar_pinned', JSON.stringify(list.slice(0, 20)))
      window.dispatchEvent(new Event('grunt_sidebar_pinned_changed'))
      loadPinnedItems()
    }
  } catch { /* ignore */ }
}

function navigatePinnedItem(item: { workspace: string; type: string; link_to: string }) {
  switch (item.type) {
    case 'DocType': router.push(`/${item.workspace}/list/${item.link_to}`); break
    case 'Report': router.push(`/${item.workspace}/report/${item.link_to}`); break
    case 'Dashboard': router.push(`/${item.workspace}/dashboard/${item.link_to}`); break
    case 'URL': window.open(item.link_to, '_blank'); break
    default: router.push(`/${item.workspace}/list/${item.link_to}`)
  }
}

function loadPinnedItems() {
  try {
    const saved = localStorage.getItem('grunt_sidebar_pinned')
    if (!saved) { pinnedItems.value = []; return }
    const ids = JSON.parse(saved) as string[]
    pinnedItems.value = ids
      .map((id) => {
        const [workspace, type, link_to] = id.split(':')
        if (!workspace || !type || !link_to) return null
        const found = wsStore.active?.items.find(i => i.type === type && i.link_to === link_to)
        return { workspace, type, link_to, label: found?.label || link_to, icon: found?.icon || '📌' }
      })
      .filter((item): item is NonNullable<typeof item> => !!item)
      .slice(0, 10)
  } catch { pinnedItems.value = [] }
}
</script>

<template>
  <Sidebar collapsible="icon">
    <!-- ── Header: Workspace Switcher ── -->
    <SidebarHeader class="p-2">
      <DropdownMenu v-if="state !== 'collapsed'">
        <DropdownMenuTrigger as-child>
          <button
            class="group w-full flex items-center justify-between px-3 py-2.5 rounded-xl border border-sidebar-border bg-gradient-to-br from-sidebar via-sidebar to-primary/5 hover:border-primary/30 hover:shadow-lg hover:shadow-primary/5 transition-all duration-300 relative overflow-hidden">
            <div
              class="absolute inset-0 bg-gradient-to-tr from-transparent via-white/5 to-white/10 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />
            <div class="flex items-center gap-3 min-w-0 relative z-10">
              <div
                class="size-9 rounded-xl bg-primary/10 flex items-center justify-center shrink-0 group-hover:scale-110 group-hover:rotate-3 transition-all duration-300 shadow-inner">
                <span class="text-xl leading-none filter drop-shadow-sm">{{ wsStore.active?.icon || '📁' }}</span>
              </div>
              <div class="flex flex-col items-start min-w-0">
                <span class="text-[10px] font-black text-primary/60 uppercase tracking-[0.2em] leading-none mb-1.5">
                  {{ wsStore.active?.name === 'grunt' ? 'СИСТЕМА' : 'РОБОЧИЙ ПРОСТІР' }}
                </span>
                <span class="text-sm font-bold text-sidebar-foreground truncate w-full group-hover:text-primary transition-colors">
                  {{ wsStore.active?.label }}
                </span>
              </div>
            </div>
            <ChevronsUpDown
              class="size-4 text-sidebar-foreground/40 group-hover:text-primary transition-all shrink-0 ml-2 group-hover:translate-y-0.5" />
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

      <!-- Collapsed: icon only -->
      <SidebarMenuButton v-else :tooltip="wsStore.active?.label || 'Workspace'" @click="goToDesk"
        class="h-10 justify-center">
        <span class="text-xl">{{ wsStore.active?.icon || '📁' }}</span>
      </SidebarMenuButton>
    </SidebarHeader>

    <!-- ── Content ── -->
    <SidebarContent>
      <!-- Search + Notifications + Pinned (hidden when collapsed) -->
      <SidebarGroup v-if="state !== 'collapsed'" class="py-2 gap-2">
        <!-- Search -->
        <button
          class="w-full flex items-center justify-between px-3.5 py-2 rounded-xl border border-sidebar-border/50 bg-muted/20 hover:bg-muted/40 hover:border-primary/30 hover:shadow-sm transition-all group overflow-hidden relative"
          @click="triggerSearch">
          <div class="absolute inset-0 bg-primary/5 opacity-0 group-hover:opacity-100 transition-opacity" />
          <div class="flex items-center gap-2.5 min-w-0 relative z-10">
            <Search class="size-4 text-muted-foreground group-hover:text-primary transition-all shrink-0" />
            <span class="text-xs font-semibold text-muted-foreground/80 group-hover:text-foreground transition-colors">
              Пошук...
            </span>
          </div>
          <div
            class="flex items-center gap-0.5 px-2 py-0.5 rounded-md border border-sidebar-border/50 bg-background/50 text-[9px] font-bold text-muted-foreground shadow-sm group-hover:border-primary/30 transition-all relative z-10">
            <span class="opacity-70 text-[10px]">⌘</span>
            <span>K</span>
          </div>
        </button>

        <!-- Notifications -->
        <NotificationsPopover :workspace="wsStore.active?.name" />

        <!-- Pinned items -->
        <div v-if="pinnedItems.length" class="space-y-1">
          <p class="px-1 text-[11px] tracking-widest font-bold uppercase text-muted-foreground">Закріплені</p>
          <div v-for="item in pinnedItems" :key="`${item.workspace}-${item.type}-${item.link_to}`"
            class="w-full flex items-center justify-between text-sm px-2 py-1 rounded hover:bg-sidebar-accent/70 transition">
            <button class="text-left flex-1 truncate" @click="navigatePinnedItem(item)">
              {{ item.icon }} {{ item.label }}
              <span class="text-[10px] text-muted-foreground lowercase ml-1">({{ item.type }})</span>
            </button>
            <button
              class="ml-2 rounded-md p-1 text-muted-foreground/60 hover:text-destructive hover:bg-destructive/10"
              @click.stop="unpinItem(item)">
              <X class="size-3" />
            </button>
          </div>
        </div>
      </SidebarGroup>

      <!-- Navigation -->
      <SidebarGroup class="py-0 px-0">
        <SidebarMenu>
          <!-- Workspace Dashboard -->
          <SidebarMenuItem>
            <RouterLink :to="`/${workspaceName}/dashboard/${workspaceName}`" custom v-slot="{ isActive, href, navigate }">
              <SidebarMenuButton :is-active="isActive" tooltip="Огляд" as="a" :href="href" @click="navigate">
                <LayoutDashboard class="shrink-0" />
                <span>Огляд</span>
              </SidebarMenuButton>
            </RouterLink>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarGroup>

      <SidebarSeparator />

      <!-- Grouped workspace items -->
      <template v-for="(group, gi) in wsStore.groupedItems" :key="gi">
        <SidebarSeparator v-if="group.section === '__divider__'" />
        <SidebarGroup v-else class="py-0 px-0">
          <SidebarGroupLabel v-if="group.section">{{ group.section }}</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarItem v-for="item in group.items" :key="item.link_to + item.sequence" :item="item"
                :workspace-name="workspaceName"
                :count="wsStore.counts[item.link_to] ?? 0"
                :color="wsStore.active?.color" />
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </template>

      <!-- Admin shortcuts -->
      <SidebarGroup v-if="state !== 'collapsed' && auth.user?.is_superadmin" class="mt-auto">
        <SidebarMenu>
          <SidebarMenuItem>
            <RouterLink :to="`/grunt/list/DocTypePermission`" custom v-slot="{ isActive, href, navigate }">
              <SidebarMenuButton :is-active="isActive" as="a" :href="href" variant="outline" size="sm" @click="navigate">
                <Shield class="shrink-0" />
                <span>Права доступу</span>
              </SidebarMenuButton>
            </RouterLink>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <RouterLink :to="`/grunt/list/ActivityLog`" custom v-slot="{ isActive, href, navigate }">
              <SidebarMenuButton :is-active="isActive" as="a" :href="href" variant="outline" size="sm" @click="navigate">
                <Activity class="shrink-0" />
                <span>Журнал активності</span>
              </SidebarMenuButton>
            </RouterLink>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <RouterLink :to="`/grunt/list/EmailAccount`" custom v-slot="{ isActive, href, navigate }">
              <SidebarMenuButton :is-active="isActive" as="a" :href="href" variant="outline" size="sm" @click="navigate">
                <Mail class="shrink-0" />
                <span>Пошта</span>
              </SidebarMenuButton>
            </RouterLink>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <SidebarMenuButton variant="outline" size="sm" @click="showEditor = true">
              <Settings2 class="shrink-0" />
              <span>Налаштувати</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarGroup>
    </SidebarContent>

    <!-- ── Footer: User menu ── -->
    <SidebarFooter class="p-2">
      <SidebarMenu>
        <SidebarMenuItem>
          <DropdownMenu>
            <DropdownMenuTrigger as-child>
              <SidebarMenuButton size="lg" :tooltip="auth.user?.full_name" class="h-auto py-1.5">
                <Avatar class="size-7 rounded-md bg-primary shrink-0">
                  <AvatarImage :src="auth.user?.avatar || ''" />
                  <AvatarFallback class="text-primary-foreground text-xs font-medium bg-transparent">
                    {{ auth.user ? initials(auth.user.full_name) : '?' }}
                  </AvatarFallback>
                </Avatar>
                <div class="flex-1 text-left min-w-0 group-data-[collapsible=icon]:hidden">
                  <p class="text-sm font-medium text-sidebar-foreground truncate leading-tight">
                    {{ auth.user?.full_name }}
                  </p>
                  <p class="text-[11px] text-muted-foreground truncate leading-tight">{{ auth.user?.email }}</p>
                </div>
                <ChevronsUpDown class="size-4 text-muted-foreground shrink-0 group-data-[collapsible=icon]:hidden" />
              </SidebarMenuButton>
            </DropdownMenuTrigger>
            <DropdownMenuContent side="top" align="start" class="w-56">
              <DropdownMenuLabel class="text-xs text-muted-foreground font-normal">Тема</DropdownMenuLabel>
              <DropdownMenuRadioGroup :model-value="colorMode.currentTheme.value"
                @update:model-value="(v) => typeof v === 'string' && onThemeChange(v)">
                <DropdownMenuRadioItem value="light"><Sun class="size-3.5 mr-2" />Світла</DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="dark"><Moon class="size-3.5 mr-2" />Темна</DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="system"><Monitor class="size-3.5 mr-2" />Системна</DropdownMenuRadioItem>
              </DropdownMenuRadioGroup>
              <DropdownMenuSeparator />
              <DropdownMenuItem @click="handleLogout">
                <LogOut class="size-4 mr-2" />Вийти
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </SidebarMenuItem>
      </SidebarMenu>
    </SidebarFooter>

    <SidebarRail />

    <SidebarEditor v-if="wsStore.active" v-model:open="showEditor" :workspace="wsStore.active"
      @saved="wsStore.setActive(workspaceName, true)" />
  </Sidebar>
</template>
