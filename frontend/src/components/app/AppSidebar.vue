<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import i18n from '@/plugins/i18n'
import { useAppStore } from '@/stores/app'
import AppIcon from '@/components/AppIcon.vue'
import NotificationsPopover from '@/components/layout/NotificationsPopover.vue'
import SidebarItem from './SidebarItem.vue'
import { useColorMode } from '@/core/composables/useColorMode'
import type { Theme } from '@/core/composables/useColorMode'
import { useSidebar } from '@/components/ui/sidebar'
import {
  ArrowLeft, Check, ChevronRight, ChevronsUpDown, Sun, Moon, Monitor,
  Settings2, Search, Activity,
  Mail, LogOut, Languages, Eye,
} from '@lucide/vue'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Sidebar, SidebarContent, SidebarGroup, SidebarGroupContent, SidebarGroupLabel, SidebarHeader, SidebarMenu, SidebarMenuButton, SidebarMenuItem, SidebarMenuSub, SidebarSeparator } from '@/components/ui/sidebar'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { DropdownMenuRadioGroup, DropdownMenuRadioItem } from '@/components/ui/dropdown-menu'
import { SidebarFooter, SidebarRail } from '@/components/ui/sidebar'
const props = defineProps<{ workspaceName: string }>()

const appStore = useAppStore()
const auth = useAuthStore()
const router = useRouter()
const colorMode = useColorMode()
const { isMobile } = useSidebar()

// ── Actions ───────────────────────────────────────────────────────────────────
function goToDesk() { router.push('/app') }
function goToProfile() { if (auth.user) router.push(`/app/grunt/User/${auth.user.id}`) }
function triggerSearch() { window.dispatchEvent(new CustomEvent('toggle-search')) }
function initials(name: string) { return name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase() }
async function onThemeChange(theme: unknown) { await auth.setTheme(theme as Theme) }
const currentLanguage = computed(() => auth.user?.language || i18n.global.locale.value)
async function onLanguageChange(lang: unknown) { await auth.setLanguage(lang as 'uk' | 'en') }
async function handleLogout() { await auth.logout(); router.push('/login') }
async function exitImpersonation() {
  await auth.stopImpersonation()
  // Full reload so every store re-initialises under the System Manager identity.
  window.location.href = '/'
}

// ── Admin shortcuts ───────────────────────────────────────────────────────────
const adminLinks = [
  { to: '/grunt/ActivityLog', icon: Activity, label: 'Журнал активності' },
  { to: '/grunt/EmailMessage', icon: Mail, label: 'Листи (e-mail)' },
  { to: '/grunt/EmailAccount', icon: Mail, label: 'Пошта — налаштування' },
]

// ── Lifecycle ─────────────────────────────────────────────────────────────────
const _onQuickCreate = () => {
  window.dispatchEvent(new CustomEvent('toggle-search'))
  window.dispatchEvent(new CustomEvent('command-palette-open-quick-create'))
}
const _onRecentDocsChanged = () => appStore.refreshCounts()

onMounted(() => {
  window.addEventListener('grunt_recent_docs_changed', _onRecentDocsChanged)
  window.addEventListener('open-quick-create', _onQuickCreate)
})

onUnmounted(() => {
  window.removeEventListener('grunt_recent_docs_changed', _onRecentDocsChanged)
  window.removeEventListener('open-quick-create', _onQuickCreate)
})

watch(() => router.currentRoute.value.path, () => { if (appStore.active) appStore.refreshCounts() })
</script>

<template>
  <Sidebar collapsible="icon">
    <SidebarHeader>
      <SidebarMenu>
        <SidebarMenuItem>
          <DropdownMenu>
            <DropdownMenuTrigger as-child>
              <SidebarMenuButton size="lg" class="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground">
                <div class="bg-sidebar-primary text-sidebar-primary-foreground flex aspect-square size-8 items-center justify-center rounded-lg">
                  <AppIcon :icon="appStore.active?.icon || 'folder'" class="size-4" />
                </div>
                <div class="grid flex-1 text-left leading-tight">
                  <span class="truncate font-semibold">{{ appStore.active?.label }}</span>
                  <span class="truncate text-muted-foreground">{{ appStore.active?.description || appStore.active?.app }}</span>
                </div>
                <ChevronsUpDown class="ml-auto" />
              </SidebarMenuButton>
            </DropdownMenuTrigger>
            <DropdownMenuContent class="w-(--reka-dropdown-menu-trigger-width) min-w-56 rounded-lg" align="start" side="bottom" :side-offset="4">
              <DropdownMenuLabel class="text-xs text-muted-foreground">Застосунки</DropdownMenuLabel>
              <DropdownMenuItem
                v-for="ws in appStore.workspaces" :key="ws.name" class="gap-2 p-2"
                @click="router.push(`/${ws.name}`)"
              >
                <div class="flex size-6 items-center justify-center rounded-md border">
                  <AppIcon :icon="ws.icon" class="size-3.5 shrink-0" />
                </div>
                <span class="truncate">{{ ws.label }}</span>
                <Check v-if="ws.name === appStore.active?.name" class="ml-auto size-4" />
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem class="gap-2 p-2" @click="goToDesk">
                <div class="flex size-6 items-center justify-center rounded-md border bg-background">
                  <ArrowLeft class="size-4" />
                </div>
                <div class="font-medium text-muted-foreground">На головну</div>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </SidebarMenuItem>
      </SidebarMenu>

      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton tooltip="Пошук" @click="triggerSearch">
            <Search />
            <span>Пошук...</span>
            <kbd class="ml-auto flex items-center gap-0.5 rounded border border-sidebar-border/50 bg-background/50 px-1.5 font-semibold text-muted-foreground group-data-[collapsible=icon]:hidden">
              <span class="opacity-70">⌘</span>K
            </kbd>
          </SidebarMenuButton>
        </SidebarMenuItem>
        <SidebarMenuItem>
          <NotificationsPopover :workspace="appStore.active?.name" />
        </SidebarMenuItem>
        <RouterLink :to="`/app/${workspaceName}`" custom v-slot="{ navigate }">
          <SidebarItem
            :item="{ type: 'DocType', link_to: '', label: 'Огляд', icon: 'layout-dashboard', section: '', sequence: 0, show_count: false, roles: '' }"
            :workspace-name="workspaceName" @click="navigate" />
        </RouterLink>
      </SidebarMenu>
    </SidebarHeader>

    <SidebarContent>
      <!-- Workspace groups -->
      <template v-for="(group, gi) in appStore.groupedItems" :key="gi">
        <SidebarSeparator v-if="group.section === '__divider__'" />

        <SidebarGroup v-else-if="!group.section">
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarItem v-for="item in group.items" :key="item.link_to + item.sequence" :item="item"
                :workspace-name="workspaceName" :count="appStore.counts[item.count_key || item.link_to] ?? 0"
                :color="appStore.active?.color" />
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <template v-else>
          <!-- Розгорнута панель: секція, що згортається -->
          <Collapsible default-open class="group-data-[collapsible=icon]:hidden">
            <SidebarGroup>
              <SidebarGroupLabel as-child>
                <CollapsibleTrigger class="group flex w-full cursor-pointer items-center">
                  <span class="truncate">{{ group.section }}</span>
                  <ChevronRight class="ml-auto size-4 shrink-0 transition-transform group-data-[state=open]:rotate-90" />
                </CollapsibleTrigger>
              </SidebarGroupLabel>
              <CollapsibleContent>
                <SidebarGroupContent>
                  <SidebarMenuSub>
                    <SidebarItem v-for="item in group.items" :key="item.link_to + item.sequence" nested :item="item"
                      :workspace-name="workspaceName" :count="appStore.counts[item.count_key || item.link_to] ?? 0"
                      :color="appStore.active?.color" />
                  </SidebarMenuSub>
                </SidebarGroupContent>
              </CollapsibleContent>
            </SidebarGroup>
          </Collapsible>

          <!-- Згорнута панель: плоский список іконок (підменю shadcn ховається в icon-режимі) -->
          <SidebarGroup class="hidden group-data-[collapsible=icon]:flex">
            <SidebarGroupContent>
              <SidebarMenu>
                <SidebarItem v-for="item in group.items" :key="item.link_to + item.sequence" :item="item"
                  :workspace-name="workspaceName" :count="appStore.counts[item.count_key || item.link_to] ?? 0"
                  :color="appStore.active?.color" />
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </template>
      </template>

      <!-- Admin shortcuts -->
      <SidebarGroup v-if="auth.isSystemManager" class="mt-auto">
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
        <!-- Референтність: суперадмін переглядає систему від імені цього користувача -->
        <SidebarMenuItem v-if="auth.isImpersonating">
          <div class="rounded-md border border-violet-500/40 bg-violet-500/10 px-2 py-1.5 group-data-[collapsible=icon]:hidden">
            <div class="flex items-center gap-1.5 font-medium text-violet-700 dark:text-violet-300">
              <Eye class="size-3.5 shrink-0" />
              <span class="truncate">Перегляд як {{ auth.user?.full_name }}</span>
            </div>
            <button
              class="mt-1.5 w-full rounded bg-violet-600 px-2 py-1 font-semibold text-white transition-colors hover:bg-violet-700"
              @click="exitImpersonation">
              Повернутися до себе
            </button>
          </div>
          <SidebarMenuButton
            class="hidden text-violet-600 group-data-[collapsible=icon]:flex dark:text-violet-400"
            tooltip="Повернутися до свого облікового запису" @click="exitImpersonation">
            <Eye />
          </SidebarMenuButton>
        </SidebarMenuItem>

        <SidebarMenuItem>
          <DropdownMenu>
            <DropdownMenuTrigger as-child>
              <SidebarMenuButton size="lg" class="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground" :tooltip="auth.user?.full_name">
                <Avatar class="size-8 rounded-lg">
                  <AvatarImage v-if="auth.user?.avatar" :src="auth.user.avatar" alt="" />
                  <AvatarFallback class="rounded-lg">
                    {{ auth.user ? initials(auth.user.full_name) : '?' }}
                  </AvatarFallback>
                </Avatar>
                <div class="grid flex-1 text-left leading-tight">
                  <span class="truncate font-medium">{{ auth.user?.full_name }}</span>
                  <span class="truncate text-muted-foreground">{{ auth.user?.email }}</span>
                </div>
                <ChevronsUpDown class="ml-auto" />
              </SidebarMenuButton>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              class="w-(--reka-dropdown-menu-trigger-width) min-w-56 rounded-lg"
              :side="isMobile ? 'bottom' : 'right'" align="end" :side-offset="4"
            >
              <DropdownMenuItem class="p-0 font-normal focus:bg-sidebar-accent" title="Відкрити мій профіль" @click="goToProfile">
                <div class="flex w-full items-center gap-2 px-1 py-1.5 text-left">
                  <Avatar class="size-8 rounded-lg">
                    <AvatarImage v-if="auth.user?.avatar" :src="auth.user.avatar" alt="" />
                    <AvatarFallback class="rounded-lg">
                      {{ auth.user ? initials(auth.user.full_name) : '?' }}
                    </AvatarFallback>
                  </Avatar>
                  <div class="grid flex-1 text-left leading-tight">
                    <span class="truncate font-semibold">{{ auth.user?.full_name }}</span>
                    <span class="truncate text-muted-foreground">{{ auth.user?.email }}</span>
                  </div>
                </div>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuLabel class="text-xs text-muted-foreground">Тема</DropdownMenuLabel>
              <DropdownMenuRadioGroup :model-value="colorMode.currentTheme.value" @update:model-value="onThemeChange">
                <DropdownMenuRadioItem value="light" class="gap-2 p-2">
                  <Sun class="size-4 shrink-0" />
                  <span>Світла</span>
                </DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="dark" class="gap-2 p-2">
                  <Moon class="size-4 shrink-0" />
                  <span>Темна</span>
                </DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="system" class="gap-2 p-2">
                  <Monitor class="size-4 shrink-0" />
                  <span>Системна</span>
                </DropdownMenuRadioItem>
              </DropdownMenuRadioGroup>
              <DropdownMenuSeparator />
              <DropdownMenuLabel class="text-xs text-muted-foreground">Мова</DropdownMenuLabel>
              <DropdownMenuRadioGroup :model-value="currentLanguage" @update:model-value="onLanguageChange">
                <DropdownMenuRadioItem value="uk" class="gap-2 p-2">
                  <Languages class="size-4 shrink-0" />
                  <span>Українська</span>
                </DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="en" class="gap-2 p-2">
                  <Languages class="size-4 shrink-0" />
                  <span>English</span>
                </DropdownMenuRadioItem>
              </DropdownMenuRadioGroup>
              <DropdownMenuSeparator />
              <DropdownMenuItem v-if="auth.isImpersonating" class="gap-2 p-2 text-violet-600 focus:text-violet-700 dark:text-violet-400" @click="exitImpersonation">
                <Eye class="size-4 shrink-0" />
                <span>Повернутися до свого облікового запису</span>
              </DropdownMenuItem>
              <DropdownMenuItem class="gap-2 p-2" @click="handleLogout">
                <LogOut class="size-4 shrink-0" />
                <span>Вийти</span>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </SidebarMenuItem>
      </SidebarMenu>
    </SidebarFooter>

    <SidebarRail />
  </Sidebar>
</template>
