<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useWorkspaceStore } from '@/stores/workspace'
import { useSidebarStore } from '@/stores/sidebar'
import AppIcon from '@/components/AppIcon.vue'
import NotificationsPopover from '@/components/layout/NotificationsPopover.vue'
import PalettePicker from '@/components/layout/PalettePicker.vue'
import SidebarItem from './SidebarItem.vue'
import SidebarEditor from './SidebarEditor.vue'
import { useColorMode } from '@/core/composables/useColorMode'
import type { Theme } from '@/core/composables/useColorMode'
import {
  ArrowLeft, ChevronsUpDown, Sun, Moon, Monitor,
  Settings2, Search, Shield, Activity,
  Mail, X, LogOut, Check, PanelLeftClose, PanelLeftOpen,
  LayoutDashboard
} from '@lucide/vue'

const props = defineProps<{ workspaceName: string }>()

const wsStore = useWorkspaceStore()
const sidebarStore = useSidebarStore()
const auth = useAuthStore()
const router = useRouter()
const colorMode = useColorMode()

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
  { key: 'light', label: 'Світла', command: () => onThemeChange('light') },
  { key: 'dark', label: 'Темна', command: () => onThemeChange('dark') },
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
    DocType: () => router.push(`/${item.workspace}/${item.link_to}`),
    Report: () => router.push(`/${item.workspace}/report/${item.link_to}`),
    Dashboard: () => router.push(`/${item.workspace}/dashboard/${item.link_to}`),
    URL: () => window.open(item.link_to, '_blank'),
  }
    ; (map[item.type] ?? map.DocType)()
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

const isCollapsed = computed(() => sidebarStore.isCollapsed)
</script>

<template>
  <div class="h-full flex flex-col bg-card border-r border-sidebar-border transition-all duration-300 relative z-20"
    :class="isCollapsed ? 'w-[72px]' : 'w-72'">
    <!-- ── Header: Workspace switcher ─────────────────────────────────────── -->
    <header class="flex flex-col gap-2 pt-1 px-1 pb-3">
      <!-- Expanded: full button + popup menu -->
      <template v-if="!isCollapsed">
        <Menu ref="wsMenuRef" :model="wsMenuItems" popup
          :pt="{ root: { class: 'rounded-xl shadow-xl p-1.5 min-w-[200px]' } }">
          <template #item="{ item, props: mp }">
            <hr v-if="item.separator" class="border-border my-1 mx-1" />
            <a v-else v-bind="mp.action"
              class="flex items-center gap-2.5 px-3 py-2 rounded-lg cursor-pointer transition-colors hover:bg-muted"
              :class="item.isActive ? 'text-primary font-medium bg-primary/5' : ''">
              <AppIcon v-if="item.icon" :icon="item.icon" class="size-4 shrink-0 text-muted-foreground" />
              <ArrowLeft v-else-if="item.key === 'back'" class="size-4 text-muted-foreground shrink-0" />
              <span class="text-sm truncate">{{ item.label }}</span>
            </a>
          </template>
        </Menu>

        <button
          class="group w-full flex items-center justify-between px-1.5 py-2.5 rounded-xl border border-sidebar-border bg-linear-to-br from-card via-card to-primary/5 hover:border-primary/30 hover:shadow-lg hover:shadow-primary/5 transition-all duration-300 relative overflow-hidden"
          @click="(e) => wsMenuRef?.toggle(e)">
          <div
            class="absolute inset-0 bg-linear-to-tr from-transparent via-white/5 to-white/10 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />
          <div class="flex items-center gap-3.5 min-w-0 relative z-10">
            <div
              class="size-10 rounded-xl bg-primary/10 flex items-center justify-center shrink-0 group-hover:scale-110 group-hover:rotate-3 transition-all duration-300 shadow-inner">
              <AppIcon :icon="wsStore.active?.icon || 'folder'" class="size-5 text-primary" />
            </div>
            <div class="flex flex-col items-start min-w-0">
              <span class="text-[9px] font-black text-primary/70 uppercase tracking-[0.25em] leading-none mb-1.5">
                {{ wsStore.active?.name === 'grunt' ? 'СИСТЕМА' : 'РОБОЧИЙ ПРОСТІР' }}
              </span>
              <span
                class="text-sm font-bold text-foreground truncate w-full group-hover:text-primary transition-colors">
                {{ wsStore.active?.label }}
              </span>
            </div>
          </div>
          <ChevronsUpDown
            class="size-4 text-muted-foreground/40 group-hover:text-primary transition-all shrink-0 ml-2" />
        </button>
      </template>

      <!-- Collapsed: icon only -->
      <button v-else
        class="h-11 w-11 mx-auto flex items-center justify-center rounded-xl bg-primary/5 text-primary hover:bg-primary/10 transition-all shadow-sm"
        @click="goToDesk" v-tooltip.right="wsStore.active?.label || 'Workspace'">
        <AppIcon :icon="wsStore.active?.icon || 'folder'" class="size-5" />
      </button>
    </header>

    <!-- ── Content ─────────────────────────────────────────────────────────── -->
    <div class="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto overflow-x-hidden scrollbar-thin">

      <!-- Search + Notifications + Pinned (expanded only) -->
      <div v-if="!isCollapsed" class="px-1 py-1 flex flex-col gap-2">
        <!-- Search -->
        <button
          class="w-full flex items-center justify-between px-1.5 py-2 rounded-xl border border-sidebar-border/50 bg-muted/20 hover:bg-muted/40 hover:border-primary/30 hover:shadow-sm transition-all group overflow-hidden relative"
          @click="triggerSearch">
          <div class="absolute inset-0 bg-primary/5 opacity-0 group-hover:opacity-100 transition-opacity" />
          <div class="flex items-center gap-3 min-w-0 relative z-10">
            <Search class="size-4 text-muted-foreground group-hover:text-primary transition-all shrink-0" />
            <span
              class="text-xs font-semibold text-muted-foreground/80 group-hover:text-foreground transition-colors">Пошук...</span>
          </div>
          <kbd
            class="flex items-center gap-0.5 px-2 py-0.5 rounded-md border border-sidebar-border/50 bg-background/50 text-[9px] font-bold text-muted-foreground relative z-10">
            <span class="opacity-70 text-[10px]">⌘</span>K
          </kbd>
        </button>

        <!-- Notifications -->
        <NotificationsPopover :workspace="wsStore.active?.name" />

        <!-- Pinned -->
        <div v-if="pinnedItems.length" class="space-y-1 mt-2">
          <p class="px-1 text-[10px] tracking-[0.2em] font-black uppercase text-muted-foreground/50">Закріплені</p>
          <div v-for="item in pinnedItems" :key="`${item.workspace}-${item.type}-${item.link_to}`"
            class="flex items-center justify-between text-sm px-1.5 py-1 rounded-xl hover:bg-primary/5 transition group/pinned">
            <button class="text-left flex-1 flex items-center gap-2 truncate" @click="navigatePinnedItem(item)">
              <AppIcon :icon="item.icon || 'file'"
                class="size-3.5 shrink-0 text-muted-foreground group-hover/pinned:text-primary transition-colors" />
              <span class="truncate text-xs font-medium">{{ item.label }}</span>
              <span
                class="text-[9px] text-muted-foreground/60 lowercase ml-1 shrink-0 group-hover/pinned:text-muted-foreground transition-colors">({{
                item.type }})</span>
            </button>
            <button
              class="ml-2 rounded-md p-1 opacity-0 group-hover/pinned:opacity-100 text-muted-foreground/60 hover:text-destructive hover:bg-destructive/10 transition-all"
              @click.stop="unpinItem(item)">
              <X class="size-3" />
            </button>
          </div>
        </div>
      </div>

      <!-- Navigation -->
      <nav class="px-1 flex flex-col gap-1">
        <!-- Dashboard -->
        <ul class="flex w-full min-w-0 flex-col gap-1 list-none p-0 m-0">
          <RouterLink :to="`/${workspaceName}/dashboard/${workspaceName}`" custom v-slot="{ isActive }">
            <SidebarItem
              :item="{ type: 'Dashboard', link_to: workspaceName, label: 'Огляд', icon: 'layout-dashboard', section: '', sequence: 0, show_count: false, show_new_btn: false, roles: '' }"
              :workspace-name="workspaceName" :collapsed="isCollapsed" />
          </RouterLink>
        </ul>

        <Divider class="!my-3 !mx-2 opacity-50" />

        <!-- Workspace groups -->
        <template v-for="(group, gi) in wsStore.groupedItems" :key="gi">
          <Divider v-if="group.section === '__divider__'" class="!my-3 !mx-2 opacity-50" />
          <div v-else class="mb-2">
            <p v-if="group.section && !isCollapsed"
              class="text-[9px] font-black tracking-[0.25em] uppercase text-muted-foreground/40 px-3 mt-5 mb-2">
              {{ group.section }}
            </p>
            <ul class="flex w-full min-w-0 flex-col gap-1 list-none p-0 m-0">
              <SidebarItem v-for="item in group.items" :key="item.link_to + item.sequence" :item="item"
                :workspace-name="workspaceName" :count="wsStore.counts[item.link_to] ?? 0"
                :color="wsStore.active?.color" :collapsed="isCollapsed" />
            </ul>
          </div>
        </template>

        <!-- Admin shortcuts -->
        <template v-if="!isCollapsed && auth.user?.is_superadmin">
          <div class="mt-auto pt-4">
            <p class="text-[9px] font-black tracking-[0.25em] uppercase text-muted-foreground/40 px-3 mb-2">Налаштування
            </p>
            <ul class="flex w-full min-w-0 flex-col gap-1 list-none p-0 m-0">
              <li v-for="link in [
                { to: '/grunt/DocTypePermission', icon: Shield, label: 'Права доступу' },
                { to: '/grunt/ActivityLog', icon: Activity, label: 'Журнал активності' },
                { to: '/grunt/EmailAccount', icon: Mail, label: 'Пошта' },
              ]" :key="link.to">
                <RouterLink :to="link.to" custom v-slot="{ isActive, navigate }">
                  <button
                    class="w-full flex items-center gap-3 px-3 py-2 rounded-xl text-[13px] font-medium transition-all"
                    :class="isActive ? 'bg-primary/10 text-primary font-bold shadow-sm' : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground'"
                    @click="navigate">
                    <component :is="link.icon" class="size-4 shrink-0" />
                    <span>{{ link.label }}</span>
                  </button>
                </RouterLink>
              </li>
              <li>
                <button
                  class="w-full flex items-center gap-3 px-3 py-2 rounded-xl text-[13px] font-medium text-muted-foreground hover:bg-muted/50 hover:text-foreground transition-all"
                  @click="showEditor = true">
                  <Settings2 class="size-4 shrink-0" />
                  <span>Редагувати меню</span>
                </button>
              </li>
            </ul>
          </div>
        </template>
      </nav>
    </div>

    <!-- ── Footer: User menu ───────────────────────────────────────────────── -->
    <footer class="pt-3 px-1 pb-1 border-t border-sidebar-border/50">
      <Menu ref="userMenuRef" :model="userMenuItems" popup
        :pt="{ root: { class: 'rounded-xl shadow-xl p-1.5 min-w-[220px]' } }">
        <template #item="{ item, props: mp }">
          <hr v-if="item.separator" class="border-border my-1 mx-1" />
          <span v-else-if="item.disabled"
            class="block px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
            {{ item.label }}
          </span>
          <!-- Palette Picker special item -->
          <PalettePicker v-else-if="item.key === 'palette'" />

          <a v-else v-bind="mp.action"
            class="flex items-center gap-2.5 px-3 py-2 rounded-lg cursor-pointer transition-colors hover:bg-muted">
            <component :is="THEME_ICONS[item.key!]" v-if="item.key && THEME_ICONS[item.key]"
              class="size-4 text-muted-foreground shrink-0" />
            <LogOut v-else-if="item.key === 'logout'" class="size-4 text-muted-foreground shrink-0" />
            <span class="text-sm flex-1">{{ item.label }}</span>
            <Check v-if="item.key && THEME_ICONS[item.key] && colorMode.currentTheme.value === item.key"
              class="size-3.5 text-primary shrink-0" />
          </a>
        </template>
      </Menu>

      <button
        class="w-full flex items-center gap-3 px-1.5 py-2 rounded-xl hover:bg-primary/5 transition-all group overflow-hidden"
        :class="isCollapsed ? 'justify-center' : ''" :title="auth.user?.full_name"
        @click="(e) => userMenuRef?.toggle(e)">
        <Avatar :image="auth.user?.avatar || undefined" :label="auth.user ? initials(auth.user.full_name) : '?'"
          shape="circle"
          class="size-10! bg-primary! text-white! text-[14px]! font-black! shrink-0 shadow-sm transition-transform group-hover:scale-105" />
        <div v-if="!isCollapsed" class="flex-1 text-left min-w-0">
          <p
            class="text-sm font-bold text-foreground truncate leading-tight mb-0.5 group-hover:text-primary transition-colors">
            {{ auth.user?.full_name }}</p>
          <p class="text-[11px] text-muted-foreground/70 truncate leading-tight">{{ auth.user?.email }}</p>
        </div>
        <ChevronsUpDown v-if="!isCollapsed"
          class="size-4 text-muted-foreground/30 group-hover:text-primary transition-all shrink-0" />
      </button>
    </footer>

    <!-- Collapse toggle (Desktop only) -->
    <button
      class="absolute top-1/2 -right-3 size-6 rounded-full border bg-card shadow-sm flex items-center justify-center text-muted-foreground/60 hover:text-primary hover:border-primary/30 transition-all hidden md:flex z-50 group/toggle"
      @click="sidebarStore.toggleCollapse">
      <PanelLeftClose v-if="!isCollapsed" class="size-3.5 transition-transform group-hover/toggle:scale-110" />
      <PanelLeftOpen v-else class="size-3.5 transition-transform group-hover/toggle:scale-110" />
    </button>

    <SidebarEditor v-if="wsStore.active" v-model:open="showEditor" :workspace="wsStore.active"
      @saved="wsStore.setActive(workspaceName, true)" />
  </div>
</template>

<style scoped>
.scrollbar-thin::-webkit-scrollbar {
  width: 4px;
}

.scrollbar-thin::-webkit-scrollbar-track {
  background: transparent;
}

.scrollbar-thin::-webkit-scrollbar-thumb {
  background: rgba(var(--primary), 0.1);
  border-radius: 10px;
}

.scrollbar-thin:hover::-webkit-scrollbar-thumb {
  background: rgba(var(--primary), 0.2);
}
</style>
