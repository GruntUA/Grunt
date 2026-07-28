<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useAppStore } from '@/stores/app'
import AppIcon from '@/components/AppIcon.vue'
import NotificationsPopover from '@/components/layout/NotificationsPopover.vue'
import PalettePicker from '@/components/layout/PalettePicker.vue'
import SidebarItem from './SidebarItem.vue'
import { useColorMode } from '@/core/composables/useColorMode'
import type { Theme } from '@/core/composables/useColorMode'
import {
  ArrowLeft, ChevronsUpDown, Sun, Moon, Monitor,
  Settings2, Search, Shield, Activity,
  Mail, X, LogOut,
} from '@lucide/vue'

const props = defineProps<{ workspaceName: string }>()

const appStore = useAppStore()
const auth = useAuthStore()
const router = useRouter()
const colorMode = useColorMode()

const pinnedItems = ref<{ workspace: string; type: string; link_to: string; label: string; icon: string }[]>([])

// ── App Switcher items ────────────────────────────────────────────────────────
interface AppSwitcherItem {
  key?: string
  label?: string
  icon?: string
  isActive?: boolean
  command?: () => void
  separator?: boolean
}
const appSwitcherItems = computed<AppSwitcherItem[]>(() => [
  ...appStore.workspaces.map(ws => ({
    key: ws.name,
    label: ws.label,
    icon: ws.icon,
    isActive: ws.name === appStore.active?.name,
    command: () => router.push(`/${ws.name}`),
  })),
  { separator: true },
  { key: 'back', label: 'На головну', command: goToDesk },
])

// ── Actions ───────────────────────────────────────────────────────────────────
function goToDesk() { router.push('/app') }
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
        const found = appStore.active?.items.find(i => i.type === type && i.link_to === link_to)
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

// ── Admin shortcuts ───────────────────────────────────────────────────────────
const adminLinks = [
  { to: '/grunt/DocTypePermission', icon: Shield, label: 'Права доступу' },
  { to: '/grunt/ActivityLog', icon: Activity, label: 'Журнал активності' },
  { to: '/grunt/EmailAccount', icon: Mail, label: 'Пошта' },
]

// ── Lifecycle ─────────────────────────────────────────────────────────────────
const _onQuickCreate = () => {
  window.dispatchEvent(new CustomEvent('toggle-search'))
  window.dispatchEvent(new CustomEvent('command-palette-open-quick-create'))
}

onMounted(() => {
  loadPinnedItems()
  window.addEventListener('grunt_sidebar_pinned_changed', loadPinnedItems)
  window.addEventListener('grunt_recent_docs_changed', () => appStore.refreshCounts())
  window.addEventListener('open-quick-create', _onQuickCreate)
})

onUnmounted(() => {
  window.removeEventListener('grunt_sidebar_pinned_changed', loadPinnedItems)
  window.removeEventListener('grunt_recent_docs_changed', () => appStore.refreshCounts())
  window.removeEventListener('open-quick-create', _onQuickCreate)
})

watch(() => appStore.active?.name, () => loadPinnedItems())
watch(() => router.currentRoute.value.path, () => { if (appStore.active) appStore.refreshCounts() })
</script>

<template>
  <Sidebar collapsible="icon">
    <SidebarHeader>
      <SidebarMenu>
        <SidebarMenuItem>
          <DropdownMenu>
            <DropdownMenuTrigger as-child>
              <SidebarMenuButton size="lg" :tooltip="appStore.active?.label || 'Workspace'">
                <div class="bg-primary/10 text-primary flex aspect-square size-8 items-center justify-center rounded-lg">
                  <AppIcon :icon="appStore.active?.icon || 'folder'" class="size-4" />
                </div>
                <div class="grid flex-1 text-left leading-tight">
                  <span class="truncate text-xs font-semibold text-primary/70 uppercase tracking-widest">
                    {{ appStore.active?.name === 'grunt' ? 'СИСТЕМА' : 'ДОДАТОК' }}
                  </span>
                  <span class="truncate font-semibold">{{ appStore.active?.label }}</span>
                </div>
                <ChevronsUpDown class="ml-auto" />
              </SidebarMenuButton>
            </DropdownMenuTrigger>
            <DropdownMenuContent class="w-(--reka-popper-anchor-width) min-w-56 rounded-lg" align="start" side="bottom">
              <template v-for="(item, idx) in appSwitcherItems" :key="idx">
                <DropdownMenuSeparator v-if="item.separator" />
                <DropdownMenuItem v-else :class="item.isActive ? 'text-primary font-medium bg-primary/5' : ''" @click="item.command?.()">
                  <AppIcon v-if="item.icon" :icon="item.icon" class="size-4 shrink-0 text-muted-foreground" />
                  <ArrowLeft v-else-if="item.key === 'back'" class="size-4 text-muted-foreground shrink-0" />
                  <span class="truncate">{{ item.label }}</span>
                </DropdownMenuItem>
              </template>
            </DropdownMenuContent>
          </DropdownMenu>
        </SidebarMenuItem>
      </SidebarMenu>
    </SidebarHeader>

    <SidebarContent>
      <!-- Search -->
      <SidebarGroup>
        <SidebarGroupContent>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton tooltip="Пошук" @click="triggerSearch">
                <Search />
                <span>Пошук...</span>
                <kbd class="ml-auto flex items-center gap-0.5 rounded border border-sidebar-border/50 bg-background/50 px-1.5 text-xs font-semibold text-muted-foreground group-data-[collapsible=icon]:hidden">
                  <span class="opacity-70">⌘</span>K
                </kbd>
              </SidebarMenuButton>
            </SidebarMenuItem>
            <SidebarMenuItem>
              <NotificationsPopover :workspace="appStore.active?.name" />
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarGroupContent>
      </SidebarGroup>

      <!-- Pinned -->
      <SidebarGroup v-if="pinnedItems.length">
        <SidebarGroupLabel>Закріплені</SidebarGroupLabel>
        <SidebarGroupContent>
          <SidebarMenu>
            <SidebarMenuItem v-for="item in pinnedItems" :key="`${item.workspace}-${item.type}-${item.link_to}`">
              <SidebarMenuButton :tooltip="item.label" @click="navigatePinnedItem(item)">
                <AppIcon :icon="item.icon || 'file'" />
                <span>{{ item.label }}</span>
              </SidebarMenuButton>
              <SidebarMenuAction show-on-hover title="Відкріпити" @click.stop="unpinItem(item)">
                <X />
              </SidebarMenuAction>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarGroupContent>
      </SidebarGroup>

      <!-- Home -->
      <SidebarGroup>
        <SidebarGroupContent>
          <SidebarMenu>
            <RouterLink :to="`/app/${workspaceName}`" custom v-slot="{ navigate }">
              <SidebarItem
                :item="{ type: 'DocType', link_to: '', label: 'Огляд', icon: 'layout-dashboard', section: '', sequence: 0, show_count: false, show_new_btn: false, roles: '' }"
                :workspace-name="workspaceName" @click="navigate" />
            </RouterLink>
          </SidebarMenu>
        </SidebarGroupContent>
      </SidebarGroup>

      <!-- Workspace groups -->
      <template v-for="(group, gi) in appStore.groupedItems" :key="gi">
        <SidebarSeparator v-if="group.section === '__divider__'" />
        <SidebarGroup v-else>
          <SidebarGroupLabel v-if="group.section">{{ group.section }}</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarItem v-for="item in group.items" :key="item.link_to + item.sequence" :item="item"
                :workspace-name="workspaceName" :count="appStore.counts[item.link_to] ?? 0"
                :color="appStore.active?.color" />
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </template>

      <!-- Admin shortcuts -->
      <SidebarGroup v-if="auth.user?.is_superadmin" class="mt-auto">
        <SidebarGroupLabel>Налаштування</SidebarGroupLabel>
        <SidebarGroupContent>
          <SidebarMenu>
            <SidebarMenuItem v-for="link in adminLinks" :key="link.to">
              <RouterLink :to="link.to" custom v-slot="{ isActive, href, navigate }">
                <SidebarMenuButton as-child :is-active="isActive" :tooltip="link.label">
                  <a :href="href" @click="navigate">
                    <component :is="link.icon" />
                    <span>{{ link.label }}</span>
                  </a>
                </SidebarMenuButton>
              </RouterLink>
            </SidebarMenuItem>
            <SidebarMenuItem>
              <SidebarMenuButton tooltip="Редагувати меню" @click="router.push(`/app/grunt/AppMenu/${appStore.active?.name}`)">
                <Settings2 />
                <span>Редагувати меню</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarGroupContent>
      </SidebarGroup>
    </SidebarContent>

    <SidebarFooter>
      <SidebarMenu>
        <SidebarMenuItem>
          <DropdownMenu>
            <DropdownMenuTrigger as-child>
              <SidebarMenuButton size="lg" :tooltip="auth.user?.full_name">
                <Avatar class="size-8 rounded-lg">
                  <AvatarImage v-if="auth.user?.avatar" :src="auth.user.avatar" alt="" />
                  <AvatarFallback class="rounded-lg bg-primary text-primary-foreground font-semibold">
                    {{ auth.user ? initials(auth.user.full_name) : '?' }}
                  </AvatarFallback>
                </Avatar>
                <div class="grid flex-1 text-left leading-tight">
                  <span class="truncate font-semibold">{{ auth.user?.full_name }}</span>
                  <span class="truncate text-xs text-muted-foreground">{{ auth.user?.email }}</span>
                </div>
                <ChevronsUpDown class="ml-auto" />
              </SidebarMenuButton>
            </DropdownMenuTrigger>
            <DropdownMenuContent class="w-(--reka-popper-anchor-width) min-w-56 rounded-lg" side="bottom" align="end">
              <DropdownMenuLabel class="text-xs font-semibold uppercase tracking-widest text-muted-foreground">Тема</DropdownMenuLabel>
              <DropdownMenuRadioGroup :model-value="colorMode.currentTheme.value" @update:model-value="onThemeChange">
                <DropdownMenuRadioItem value="light" class="gap-2.5 pl-8 pr-3 py-2 rounded-lg">
                  <Sun class="size-4 text-muted-foreground shrink-0" />
                  <span class="text-sm">Світла</span>
                </DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="dark" class="gap-2.5 pl-8 pr-3 py-2 rounded-lg">
                  <Moon class="size-4 text-muted-foreground shrink-0" />
                  <span class="text-sm">Темна</span>
                </DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="system" class="gap-2.5 pl-8 pr-3 py-2 rounded-lg">
                  <Monitor class="size-4 text-muted-foreground shrink-0" />
                  <span class="text-sm">Системна</span>
                </DropdownMenuRadioItem>
              </DropdownMenuRadioGroup>
              <DropdownMenuSeparator class="my-1 mx-1" />
              <DropdownMenuLabel class="text-xs font-semibold uppercase tracking-widest text-muted-foreground">Акцент</DropdownMenuLabel>
              <div class="px-1 py-1"><PalettePicker /></div>
              <DropdownMenuSeparator class="my-1 mx-1" />
              <DropdownMenuItem class="gap-2.5 px-3 py-2 rounded-lg" @click="handleLogout">
                <LogOut class="size-4 text-muted-foreground shrink-0" />
                <span class="text-sm">Вийти</span>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </SidebarMenuItem>
      </SidebarMenu>
    </SidebarFooter>

    <SidebarRail />
  </Sidebar>
</template>
