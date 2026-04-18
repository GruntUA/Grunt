<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import type { SidebarProps } from '@/components/ui/sidebar'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from '@/components/ui/sidebar'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import {
  Home,
  Search,
  Bell,
  Settings2,
  Shield,
  Activity,
  Mail,
  ChevronsUpDown,
  LogOut,
  Sun,
  Moon,
  Monitor,
} from '@lucide/vue'

import { useAuthStore } from '@/stores/auth'
import { useWorkspaceStore } from '@/stores/workspace'
import { useColorMode, type Theme } from '@/core/composables/useColorMode'

import NavFavorites from '@/components/NavFavorites.vue'
import NavMain from '@/components/NavMain.vue'
import NavSecondary from '@/components/NavSecondary.vue'
import NavWorkspaces from '@/components/NavWorkspaces.vue'
import TeamSwitcher from '@/components/TeamSwitcher.vue'

const props = defineProps<SidebarProps>()

const auth = useAuthStore()
const wsStore = useWorkspaceStore()
const colorMode = useColorMode()
const router = useRouter()

// ── Pinned items from localStorage ──────────────────────────────────────────

const pinnedItems = ref<{ name: string; url: string; icon: string }[]>([])

function loadPinned() {
  try {
    const saved = localStorage.getItem('grunt_sidebar_pinned')
    if (!saved) { pinnedItems.value = []; return }
    pinnedItems.value = (JSON.parse(saved) as string[])
      .map((id) => {
        const [workspace, type, link_to] = id.split(':')
        if (!workspace || !type || !link_to) return null
        const url = type === 'Report'
          ? `/${workspace}/report/${link_to}`
          : type === 'Dashboard'
            ? `/${workspace}/dashboard/${link_to}`
            : `/${workspace}/list/${link_to}`
        const found = wsStore.workspaces
          .find(w => w.name === workspace)?.items
          ?.find(i => i.link_to === link_to)
        return { name: found?.label || link_to, url, icon: found?.icon || 'pin' }
      })
      .filter((i): i is NonNullable<typeof i> => !!i)
      .slice(0, 10)
  } catch { pinnedItems.value = [] }
}

function handleUnpin(item: { name: string; url: string; icon: string }) {
  const parts = item.url.split('/')
  const workspace = parts[1] ?? ''
  const link_to = parts[parts.length - 1] ?? ''
  const type = item.url.includes('/report/') ? 'Report'
    : item.url.includes('/dashboard/') ? 'Dashboard'
    : 'DocType'
  try {
    const key = `${workspace}:${type}:${link_to}`
    const list = JSON.parse(localStorage.getItem('grunt_sidebar_pinned') || '[]') as string[]
    const idx = list.indexOf(key)
    if (idx >= 0) list.splice(idx, 1)
    localStorage.setItem('grunt_sidebar_pinned', JSON.stringify(list))
    window.dispatchEvent(new Event('grunt_sidebar_pinned_changed'))
  } catch { /* ignore */ }
}

onMounted(() => {
  wsStore.loadAll()
  loadPinned()
  window.addEventListener('grunt_sidebar_pinned_changed', loadPinned)
})
onUnmounted(() => window.removeEventListener('grunt_sidebar_pinned_changed', loadPinned))

// ── Nav data ─────────────────────────────────────────────────────────────────

const workspacesForSwitcher = computed(() =>
  wsStore.workspaces.map(ws => ({
    name: ws.label || ws.name,
    icon: ws.icon || 'folder',
    url: `/${ws.name}`,
  }))
)

const navMain = [
  { title: 'Головна', url: '/', icon: Home },
  { title: 'Пошук', url: '#search', icon: Search },
  { title: 'Сповіщення', url: '#notifications', icon: Bell },
]

const navSecondary = computed(() => [
  { title: 'Налаштування', url: '/grunt/list/SystemSettings/SystemSettings', icon: Settings2 },
  ...(auth.user?.is_superadmin ? [
    { title: 'Права доступу', url: '/grunt/list/DocTypePermission', icon: Shield },
    { title: 'Журнал активності', url: '/grunt/list/ActivityLog', icon: Activity },
    { title: 'Пошта', url: '/grunt/list/EmailAccount', icon: Mail },
  ] : []),
])

const workspacesForNav = computed(() =>
  wsStore.workspaces.map(ws => ({
    name: ws.label || ws.name,
    icon: ws.icon || 'folder',
    pages: (ws.items || []).slice(0, 6).map(item => ({
      name: item.label || item.link_to,
      url: `/${ws.name}/list/${item.link_to}`,
      icon: item.icon || 'file',
    })),
  }))
)

// ── User ──────────────────────────────────────────────────────────────────────

function initials(name: string) {
  return name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
}

async function handleLogout() {
  await auth.logout()
  router.push('/login')
}
</script>

<template>
  <Sidebar class="border-r-0" v-bind="props">
    <!-- Header: Workspace switcher + primary nav -->
    <SidebarHeader>
      <TeamSwitcher :workspaces="workspacesForSwitcher" />
      <NavMain :items="navMain" />
    </SidebarHeader>

    <!-- Content: Pinned + Workspaces + Secondary -->
    <SidebarContent>
      <NavFavorites v-if="pinnedItems.length" :favorites="pinnedItems" @unpin="handleUnpin" />
      <NavWorkspaces :workspaces="workspacesForNav" />
      <NavSecondary :items="navSecondary" class="mt-auto" />
    </SidebarContent>

    <!-- Footer: User profile -->
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
                  <p class="text-sm font-medium truncate leading-tight">{{ auth.user?.full_name }}</p>
                  <p class="text-[11px] text-muted-foreground truncate leading-tight">{{ auth.user?.email }}</p>
                </div>
                <ChevronsUpDown class="size-4 text-muted-foreground shrink-0 group-data-[collapsible=icon]:hidden" />
              </SidebarMenuButton>
            </DropdownMenuTrigger>
            <DropdownMenuContent side="top" align="start" class="w-56">
              <DropdownMenuRadioGroup
                :model-value="colorMode.currentTheme.value"
                @update:model-value="(v) => typeof v === 'string' && auth.setTheme(v as Theme)"
              >
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
  </Sidebar>
</template>
