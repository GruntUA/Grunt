<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useWorkspaceStore } from '@/stores/workspace'
import AppIcon from '@/components/AppIcon.vue'
import NotificationsPopover from '@/components/layout/NotificationsPopover.vue'
import PalettePicker from '@/components/layout/PalettePicker.vue'
import { Sidebar, SidebarRail, SidebarMenuButton, useSidebar } from '@/components/ui/sidebar'
import SidebarItem from './SidebarItem.vue'
import SidebarEditor from './SidebarEditor.vue'
import { useColorMode } from '@/core/composables/useColorMode'
import type { Theme } from '@/core/composables/useColorMode'
import {
  ArrowLeft, ChevronsUpDown, Sun, Moon, Monitor,
  Settings2, Search, Shield, LayoutDashboard, Activity,
  Mail, X, LogOut, Check,
} from '@lucide/vue'

defineProps<{ workspaceName: string }>()

const wsStore = useWorkspaceStore()
const auth = useAuthStore()
const router = useRouter()
const colorMode = useColorMode()
const { state } = useSidebar()

const showEditor = ref(false)
const pinnedItems = ref<{ workspace: string; type: string; link_to: string; label: string; icon: string }[]>([])

// ── PrimeVue Menu refs ────────────────────────────────────────────────────────
const wsMenuRef = ref()
const userMenuRef = ref()

// ── Workspace dropdown items ──────────────────────────────────────────────────
const wsMenuItems = computed(() => [
  ...wsStore.workspaces.map(ws => ({
    key: ws.name,
    label: ws.label,
    icon: ws.icon,
    isActive: ws.name === wsStore.active?.name,
    command: () => router.push(`/${ws.name}`),
  })),
  { separator: true },
  { key: 'back', label: 'На головну', command: goToDesk },
])

// ── User dropdown items ───────────────────────────────────────────────────────
const userMenuItems = computed(() => [
  { key: '__theme_label', label: 'Тема', disabled: true },
  { key: 'light',  label: 'Світла',   command: () => onThemeChange('light') },
  { key: 'dark',   label: 'Темна',    command: () => onThemeChange('dark') },
  { key: 'system', label: 'Системна', command: () => onThemeChange('system') },
  { separator: true },
  { key: '__palette_label', label: 'Акцент', disabled: true },
  { key: 'palette' },
  { separator: true },
  { key: 'logout', label: 'Вийти', command: handleLogout },
])

const THEME_ICONS: Record<string, any> = { light: Sun, dark: Moon, system: Monitor }

// ── Actions ───────────────────────────────────────────────────────────────────
function goToDesk() { router.push('/') }
function triggerSearch() { window.dispatchEvent(new CustomEvent('toggle-search')) }
function initials(name: string) { return name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase() }
async function onThemeChange(theme: string) { await auth.setTheme(theme as Theme) }
async function handleLogout() { await auth.logout(); router.push('/login') }

// ── Pinned items ──────────────────────────────────────────────────────────────
function loadPinnedItems() {
  try {
    const saved = localStorage.getItem('grunt_sidebar_pinned')
    if (!saved) { pinnedItems.value = []; return }
    pinnedItems.value = (JSON.parse(saved) as string[])
      .map(id => {
        const [workspace, type, link_to] = id.split(':')
        if (!workspace || !type || !link_to) return null
        const found = wsStore.active?.items.find(i => i.type === type && i.link_to === link_to)
        return { workspace, type, link_to, label: found?.label || link_to, icon: found?.icon || '📌' }
      })
      .filter((i): i is NonNullable<typeof i> => !!i)
      .slice(0, 10)
  } catch { pinnedItems.value = [] }
}

function unpinItem(item: { workspace: string; type: string; link_to: string }) {
  try {
    const saved = localStorage.getItem('grunt_sidebar_pinned')
    if (!saved) return
    const list = JSON.parse(saved) as string[]
    const idx = list.indexOf(`${item.workspace}:${item.type}:${item.link_to}`)
    if (idx >= 0) {
      list.splice(idx, 1)
      localStorage.setItem('grunt_sidebar_pinned', JSON.stringify(list))
      window.dispatchEvent(new Event('grunt_sidebar_pinned_changed'))
      loadPinnedItems()
    }
  } catch { /* ignore */ }
}

function navigatePinnedItem(item: { workspace: string; type: string; link_to: string }) {
  const map: Record<string, () => void> = {
    DocType:   () => router.push(`/${item.workspace}/${item.link_to}`),
    Report:    () => router.push(`/${item.workspace}/report/${item.link_to}`),
    Dashboard: () => router.push(`/${item.workspace}/dashboard/${item.link_to}`),
    URL:       () => window.open(item.link_to, '_blank'),
  }
  ;(map[item.type] ?? map.DocType)()
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────
const _onQuickCreate = () => {
  window.dispatchEvent(new CustomEvent('toggle-search'))
  window.dispatchEvent(new CustomEvent('command-palette-open-quick-create'))
}

onMounted(() => {
  loadPinnedItems()
  window.addEventListener('grunt_sidebar_pinned_changed', loadPinnedItems)
  window.addEventListener('grunt_recent_docs_changed', () => wsStore.refreshCounts())
  window.addEventListener('open-quick-create', _onQuickCreate)
})

onUnmounted(() => {
  window.removeEventListener('grunt_sidebar_pinned_changed', loadPinnedItems)
  window.removeEventListener('grunt_recent_docs_changed', () => wsStore.refreshCounts())
  window.removeEventListener('open-quick-create', _onQuickCreate)
})

watch(() => wsStore.active?.name, () => loadPinnedItems())
watch(() => router.currentRoute.value.path, () => { if (wsStore.active) wsStore.refreshCounts() })
</script>

<template>
  <Sidebar collapsible="icon">

    <!-- ── Header: Workspace switcher ─────────────────────────────────────── -->
    <header class="flex flex-col gap-2 p-2">
      <!-- Expanded: full button + popup menu -->
      <template v-if="state !== 'collapsed'">
        <Menu ref="wsMenuRef" :model="wsMenuItems" popup
          :pt="{ root: { class: 'rounded-xl shadow-xl p-1.5 min-w-[200px]' } }">
          <template #item="{ item, props: mp }">
            <hr v-if="item.separator" class="border-border my-1 mx-1" />
            <a v-else v-bind="mp.action" class="flex items-center gap-2.5 px-3 py-2 rounded-lg cursor-pointer transition-colors hover:bg-muted"
              :class="item.isActive ? 'text-primary font-medium bg-primary/5' : ''">
              <AppIcon v-if="item.icon" :icon="item.icon" class="size-4 shrink-0 text-muted-foreground" />
              <ArrowLeft v-else-if="item.key === 'back'" class="size-4 text-muted-foreground shrink-0" />
              <span class="text-sm truncate">{{ item.label }}</span>
            </a>
          </template>
        </Menu>

        <button
          class="group w-full flex items-center justify-between px-3 py-2.5 rounded-xl border border-sidebar-border bg-linear-to-br from-sidebar via-sidebar to-primary/5 hover:border-primary/30 hover:shadow-lg hover:shadow-primary/5 transition-all duration-300 relative overflow-hidden"
          @click="(e) => wsMenuRef?.toggle(e)">
          <div class="absolute inset-0 bg-linear-to-tr from-transparent via-white/5 to-white/10 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />
          <div class="flex items-center gap-3 min-w-0 relative z-10">
            <div class="size-9 rounded-xl bg-primary/10 flex items-center justify-center shrink-0 group-hover:scale-110 group-hover:rotate-3 transition-all duration-300 shadow-inner">
              <AppIcon :icon="wsStore.active?.icon || 'folder'" class="size-5 text-primary" />
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
          <ChevronsUpDown class="size-4 text-sidebar-foreground/40 group-hover:text-primary transition-all shrink-0 ml-2" />
        </button>
      </template>

      <!-- Collapsed: icon only -->
      <SidebarMenuButton v-else :tooltip="wsStore.active?.label || 'Workspace'" class="h-10 justify-center" @click="goToDesk">
        <AppIcon :icon="wsStore.active?.icon || 'folder'" class="size-5" />
      </SidebarMenuButton>
    </header>

    <!-- ── Content ─────────────────────────────────────────────────────────── -->
    <div class="flex min-h-0 flex-1 flex-col gap-2 overflow-auto group-data-[collapsible=icon]:overflow-hidden">

      <!-- Search + Notifications + Pinned (expanded only) -->
      <div v-if="state !== 'collapsed'" class="px-2 py-1 flex flex-col gap-2">
        <!-- Search -->
        <button
          class="w-full flex items-center justify-between px-3.5 py-2 rounded-xl border border-sidebar-border/50 bg-muted/20 hover:bg-muted/40 hover:border-primary/30 hover:shadow-sm transition-all group overflow-hidden relative"
          @click="triggerSearch">
          <div class="absolute inset-0 bg-primary/5 opacity-0 group-hover:opacity-100 transition-opacity" />
          <div class="flex items-center gap-2.5 min-w-0 relative z-10">
            <Search class="size-4 text-muted-foreground group-hover:text-primary transition-all shrink-0" />
            <span class="text-xs font-semibold text-muted-foreground/80 group-hover:text-foreground transition-colors">Пошук...</span>
          </div>
          <kbd class="flex items-center gap-0.5 px-2 py-0.5 rounded-md border border-sidebar-border/50 bg-background/50 text-[9px] font-bold text-muted-foreground relative z-10">
            <span class="opacity-70 text-[10px]">⌘</span>K
          </kbd>
        </button>

        <!-- Notifications -->
        <NotificationsPopover :workspace="wsStore.active?.name" />

        <!-- Pinned -->
        <div v-if="pinnedItems.length" class="space-y-1">
          <p class="px-1 text-[11px] tracking-widest font-bold uppercase text-muted-foreground">Закріплені</p>
          <div v-for="item in pinnedItems" :key="`${item.workspace}-${item.type}-${item.link_to}`"
            class="flex items-center justify-between text-sm px-2 py-1 rounded hover:bg-sidebar-accent/70 transition">
            <button class="text-left flex-1 flex items-center gap-1.5 truncate" @click="navigatePinnedItem(item)">
              <AppIcon :icon="item.icon || 'file'" class="size-3.5 shrink-0 text-muted-foreground" />
              {{ item.label }}
              <span class="text-[10px] text-muted-foreground lowercase ml-1">({{ item.type }})</span>
            </button>
            <button class="ml-2 rounded-md p-1 text-muted-foreground/60 hover:text-destructive hover:bg-destructive/10" @click.stop="unpinItem(item)">
              <X class="size-3" />
            </button>
          </div>
        </div>
      </div>

      <!-- Navigation -->
      <nav class="px-2 flex flex-col gap-1">
        <!-- Dashboard -->
        <ul class="flex w-full min-w-0 flex-col gap-1">
          <li class="group/menu-item relative">
            <RouterLink :to="`/${workspaceName}/dashboard/${workspaceName}`" custom v-slot="{ isActive, href, navigate }">
              <SidebarMenuButton :is-active="isActive" tooltip="Огляд" as="a" :href="href" @click="navigate">
                <LayoutDashboard class="shrink-0" />
                <span>Огляд</span>
              </SidebarMenuButton>
            </RouterLink>
          </li>
        </ul>

        <hr class="bg-sidebar-border border-none h-px mx-0 my-1" />

        <!-- Workspace groups -->
        <template v-for="(group, gi) in wsStore.groupedItems" :key="gi">
          <hr v-if="group.section === '__divider__'" class="bg-sidebar-border border-none h-px mx-0 my-1" />
          <div v-else>
            <p v-if="group.section"
              class="text-sidebar-foreground/70 flex h-8 shrink-0 items-center rounded-md px-2 text-xs font-medium transition-[margin,opacity] duration-200 ease-linear group-data-[collapsible=icon]:-mt-8 group-data-[collapsible=icon]:opacity-0">
              {{ group.section }}
            </p>
            <ul class="flex w-full min-w-0 flex-col gap-1">
              <SidebarItem
                v-for="item in group.items"
                :key="item.link_to + item.sequence"
                :item="item"
                :workspace-name="workspaceName"
                :count="wsStore.counts[item.link_to] ?? 0"
                :color="wsStore.active?.color"
              />
            </ul>
          </div>
        </template>

        <!-- Admin shortcuts -->
        <template v-if="state !== 'collapsed' && auth.user?.is_superadmin">
          <hr class="bg-sidebar-border border-none h-px mx-0 mt-auto mb-1" />
          <ul class="flex w-full min-w-0 flex-col gap-1">
            <li v-for="link in [
              { to: '/grunt/DocTypePermission', icon: Shield, label: 'Права доступу' },
              { to: '/grunt/ActivityLog',       icon: Activity, label: 'Журнал активності' },
              { to: '/grunt/EmailAccount',      icon: Mail,    label: 'Пошта' },
            ]" :key="link.to" class="group/menu-item relative">
              <RouterLink :to="link.to" custom v-slot="{ isActive, href, navigate }">
                <SidebarMenuButton :is-active="isActive" as="a" :href="href" variant="outline" size="sm" @click="navigate">
                  <component :is="link.icon" class="shrink-0" />
                  <span>{{ link.label }}</span>
                </SidebarMenuButton>
              </RouterLink>
            </li>
            <li class="group/menu-item relative">
              <SidebarMenuButton variant="outline" size="sm" @click="showEditor = true">
                <Settings2 class="shrink-0" />
                <span>Налаштувати</span>
              </SidebarMenuButton>
            </li>
          </ul>
        </template>
      </nav>
    </div>

    <!-- ── Footer: User menu ───────────────────────────────────────────────── -->
    <footer class="p-2 border-t border-sidebar-border/50">
      <Menu ref="userMenuRef" :model="userMenuItems" popup
        :pt="{ root: { class: 'rounded-xl shadow-xl p-1.5 min-w-[220px]' } }">
        <template #item="{ item, props: mp }">
          <hr v-if="item.separator" class="border-border my-1 mx-1" />
          <span v-else-if="item.disabled" class="block px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
            {{ item.label }}
          </span>
          <!-- Palette Picker special item -->
          <PalettePicker v-else-if="item.key === 'palette'" />

          <a v-else v-bind="mp.action" class="flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-colors hover:bg-muted">
            <component :is="THEME_ICONS[item.key!]" v-if="item.key && THEME_ICONS[item.key]" class="size-3.5 text-muted-foreground shrink-0" />
            <LogOut v-else-if="item.key === 'logout'" class="size-4 text-muted-foreground shrink-0" />
            <span class="text-sm flex-1">{{ item.label }}</span>
            <Check v-if="item.key && THEME_ICONS[item.key] && colorMode.currentTheme.value === item.key"
              class="size-3 text-primary shrink-0" />
          </a>
        </template>
      </Menu>

      <button
        class="w-full flex items-center gap-3 px-2 py-1.5 rounded-lg hover:bg-sidebar-accent/60 transition-colors group"
        :class="state === 'collapsed' ? 'justify-center' : ''"
        :title="auth.user?.full_name"
        @click="(e) => userMenuRef?.toggle(e)">
        <Avatar
          :image="auth.user?.avatar || undefined"
          :label="auth.user ? initials(auth.user.full_name) : '?'"
          shape="square"
          :pt="{ root: { class: 'size-7 rounded-md bg-primary text-primary-foreground text-xs font-medium shrink-0' } }"
        />
        <div v-if="state !== 'collapsed'" class="flex-1 text-left min-w-0">
          <p class="text-sm font-medium text-sidebar-foreground truncate leading-tight">{{ auth.user?.full_name }}</p>
          <p class="text-[11px] text-muted-foreground truncate leading-tight">{{ auth.user?.email }}</p>
        </div>
        <ChevronsUpDown v-if="state !== 'collapsed'" class="size-4 text-muted-foreground shrink-0" />
      </button>
    </footer>

    <SidebarRail />

    <SidebarEditor
      v-if="wsStore.active"
      v-model:open="showEditor"
      :workspace="wsStore.active"
      @saved="wsStore.setActive(workspaceName, true)"
    />
  </Sidebar>
</template>
