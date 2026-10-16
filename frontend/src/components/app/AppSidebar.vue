<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import i18n from '@/plugins/i18n'
import { useAppStore, type SidebarGroup as SidebarGroupT } from '@/stores/app'
import AppIcon from '@/components/AppIcon.vue'
import { Kbd, KbdGroup } from '@/components/ui/kbd'
import { shortcutKeys } from '@/core/shortcuts'
import NotificationsPopover from '@/components/layout/NotificationsPopover.vue'
import SidebarItem from './SidebarItem.vue'
import SidebarModule from './SidebarModule.vue'
import SidebarUser from './SidebarUser.vue'
import { useColorMode, type Theme } from '@/core/composables/useColorMode'
import { useSiteConfig } from '@/core/composables/useSiteConfig'
import { clearClientCache } from '@/core/clearCache'
import { appUrl } from '@/core/workspaceUrl'
import { useEventListener } from '@vueuse/core'
import {
  ArrowLeft, ChevronRight, ChevronsUpDown, LayoutDashboard, LayoutGrid, Sun, Moon, Monitor,
  Settings2, Search, LogOut, Languages, Eye, RefreshCw,
} from '@lucide/vue'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList, CommandSeparator } from '@/components/ui/command'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuRadioGroup,
  DropdownMenuRadioItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupContent, SidebarGroupLabel, SidebarHeader,
  SidebarMenu, SidebarMenuButton, SidebarMenuItem, SidebarMenuSub, SidebarRail, SidebarSeparator, useSidebar,
} from '@/components/ui/sidebar'
import { Button } from '@/components/ui/button'

defineProps<{ workspaceName: string }>()

const appStore = useAppStore()
const auth = useAuthStore()
const router = useRouter()
const colorMode = useColorMode()
const { isMobile } = useSidebar()
const { t } = useI18n()

const switcherOpen = ref(false)
function openApp(name: string | null) {
  switcherOpen.value = false
  router.push(name ? appUrl({ type: 'Workspace', name }) : '/app')
}
function goToProfile() { if (auth.user) router.push(`/app/grunt/User/${auth.user.id}`) }
function triggerSearch() { window.dispatchEvent(new CustomEvent('toggle-search')) }
async function onThemeChange(theme: unknown) { await auth.setTheme(theme as Theme) }
const currentLanguage = computed(() => auth.user?.language || i18n.global.locale.value)
const { languages } = useSiteConfig()
async function onLanguageChange(lang: unknown) { await auth.setLanguage(String(lang)) }
async function handleLogout() { await auth.logout(); router.push('/login') }
async function exitImpersonation() {
  await auth.stopImpersonation()
  // Full reload so every store re-initialises under the System Manager identity.
  window.location.href = '/'
}

useEventListener(window, 'grunt_recent_docs_changed', () => appStore.refreshCounts())
useEventListener(window, 'open-quick-create', () => {
  window.dispatchEvent(new CustomEvent('toggle-search'))
  window.dispatchEvent(new CustomEvent('command-palette-open-quick-create'))
})
watch(() => router.currentRoute.value.path, () => { if (appStore.active) appStore.refreshCounts() })

// Sidebar items as blocks: dividers, items outside any section, and runs of
// sections. A run renders as collapsible groups, or in modules mode (AppMenu
// sidebar_mode) as one row per section whose items open beside the sidebar.
type Block =
  | { kind: 'divider' }
  | { kind: 'plain'; items: SidebarGroupT['items'] }
  | { kind: 'sections'; groups: SidebarGroupT[] }

const modulesMode = computed(() => appStore.active?.sidebar_mode === 'modules')
const blocks = computed<Block[]>(() => {
  const out: Block[] = []
  for (const g of appStore.groupedItems) {
    if (g.section === '__divider__') out.push({ kind: 'divider' })
    else if (!g.section) out.push({ kind: 'plain', items: g.items })
    else {
      const last = out.at(-1)
      if (last?.kind === 'sections') last.groups.push(g)
      else out.push({ kind: 'sections', groups: [g] })
    }
  }
  return out
})
function sectionIcon(section: string) {
  return appStore.active?.sections?.find((s) => s.section === section)?.icon ?? ''
}

// On mobile the sidebar is a sheet: a module opens in place, with a way back.
const drill = ref<string | null>(null)
const drillGroup = computed(() => appStore.groupedItems.find((g) => g.section === drill.value) ?? null)
watch(() => appStore.active?.name, () => { drill.value = null })
</script>

<template>
  <Sidebar collapsible="icon">
    <SidebarHeader>
      <SidebarMenu>
        <SidebarMenuItem>
          <!-- App switcher: a searchable grid of the apps, like the desk -->
          <Popover v-model:open="switcherOpen">
            <PopoverTrigger as-child>
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
            </PopoverTrigger>
            <PopoverContent class="w-80 p-0" align="start" :side-offset="4">
              <Command>
                <CommandInput :placeholder="t('Search apps...')" />
                <CommandList class="max-h-96">
                  <CommandEmpty>{{ t('Nothing found') }}</CommandEmpty>
                  <CommandGroup :heading="t('Apps')">
                    <div class="grid grid-cols-3 gap-1">
                      <CommandItem
                        v-for="ws in appStore.workspaces" :key="ws.name" :value="ws.name"
                        class="flex-col gap-1.5 py-3 text-center"
                        :data-current="ws.name === appStore.active?.name || undefined"
                        @select="openApp(ws.name)"
                      >
                        <div
                          class="flex size-9 items-center justify-center rounded-md border bg-background"
                          :class="ws.name === appStore.active?.name && 'ring-2 ring-ring'"
                        >
                          <AppIcon :icon="ws.icon" class="size-4" />
                        </div>
                        <span class="w-full truncate text-xs">{{ ws.label }}</span>
                      </CommandItem>
                    </div>
                  </CommandGroup>
                  <CommandSeparator />
                  <CommandGroup>
                    <CommandItem value="__desk" @select="openApp(null)">
                      <LayoutGrid />
                      {{ t('All apps') }}
                    </CommandItem>
                  </CommandGroup>
                </CommandList>
              </Command>
            </PopoverContent>
          </Popover>
        </SidebarMenuItem>
      </SidebarMenu>

      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton :tooltip="t('Search')" @click="triggerSearch">
            <Search />
            <span>{{ t('Search...') }}</span>
            <KbdGroup class="ml-auto group-data-[collapsible=icon]:hidden"><Kbd v-for="key in shortcutKeys('Mod+K')" :key="key">{{ key }}</Kbd></KbdGroup>
          </SidebarMenuButton>
        </SidebarMenuItem>
        <SidebarMenuItem>
          <NotificationsPopover :workspace="appStore.active?.name" />
        </SidebarMenuItem>
        <SidebarMenuItem>
          <RouterLink :to="appUrl({ type: 'Workspace', name: workspaceName })" custom v-slot="{ isExactActive, href, navigate }">
            <SidebarMenuButton as-child :is-active="isExactActive" :tooltip="t('Overview')">
              <a :href="href" @click="navigate">
                <LayoutDashboard />
                <span>{{ t('Overview') }}</span>
              </a>
            </SidebarMenuButton>
          </RouterLink>
        </SidebarMenuItem>
      </SidebarMenu>
    </SidebarHeader>

    <SidebarContent>
      <!-- Modules mode, mobile: inside one module -->
      <SidebarGroup v-if="modulesMode && isMobile && drillGroup">
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton @click="drill = null">
              <ArrowLeft />
              <span>{{ t('Back') }}</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
        <SidebarGroupLabel>{{ drillGroup.section }}</SidebarGroupLabel>
        <SidebarGroupContent>
          <SidebarMenu>
            <SidebarItem v-for="item in drillGroup.items" :key="item.link_to + item.sequence" :item="item" :workspace-name="workspaceName" />
          </SidebarMenu>
        </SidebarGroupContent>
      </SidebarGroup>

      <template v-else>
        <template v-for="(block, bi) in blocks" :key="bi">
          <SidebarSeparator v-if="block.kind === 'divider'" />

          <SidebarGroup v-else-if="block.kind === 'plain'">
            <SidebarGroupContent>
              <SidebarMenu>
                <SidebarItem v-for="item in block.items" :key="item.link_to + item.sequence" :item="item" :workspace-name="workspaceName" />
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>

          <!-- Modules mode: one row per section -->
          <SidebarGroup v-else-if="modulesMode">
            <SidebarGroupContent>
              <SidebarMenu>
                <SidebarModule
                  v-for="g in block.groups" :key="g.section"
                  :section="g.section" :icon="sectionIcon(g.section)" :items="g.items" :workspace-name="workspaceName"
                  @drill="drill = g.section"
                />
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>

          <!-- Sections mode: collapsible groups -->
          <template v-else>
            <template v-for="group in block.groups" :key="group.section">
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
                        <SidebarItem v-for="item in group.items" :key="item.link_to + item.sequence" nested :item="item" :workspace-name="workspaceName" />
                      </SidebarMenuSub>
                    </SidebarGroupContent>
                  </CollapsibleContent>
                </SidebarGroup>
              </Collapsible>

              <!-- Згорнута панель: плоский список іконок (підменю shadcn ховається в icon-режимі) -->
              <SidebarGroup class="hidden group-data-[collapsible=icon]:flex">
                <SidebarGroupContent>
                  <SidebarMenu>
                    <SidebarItem v-for="item in group.items" :key="item.link_to + item.sequence" :item="item" :workspace-name="workspaceName" />
                  </SidebarMenu>
                </SidebarGroupContent>
              </SidebarGroup>
            </template>
          </template>
        </template>
      </template>

      <SidebarGroup v-if="auth.isSystemManager" class="mt-auto">
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton :tooltip="t('Edit menu')" @click="router.push(`/app/grunt/AppMenu/${appStore.active?.name}`)">
              <Settings2 />
              <span>{{ t('Edit menu') }}</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarGroup>
    </SidebarContent>

    <SidebarFooter>
      <SidebarMenu>
        <!-- Референтність: суперадмін переглядає систему від імені цього користувача -->
        <SidebarMenuItem v-if="auth.isImpersonating">
          <div class="rounded-md border border-violet-500/40 bg-violet-500/10 px-2 py-1.5 group-data-[collapsible=icon]:hidden">
            <div class="flex items-center gap-1.5 font-medium text-violet-700 dark:text-violet-300">
              <Eye class="size-3.5 shrink-0" />
              <span class="truncate">{{ t('Viewing as {name}', { name: auth.user?.full_name ?? '' }) }}</span>
            </div>
            <Button size="xs" class="mt-1.5 w-full" @click="exitImpersonation">
              {{ t('switch back') }}
            </Button>
          </div>
          <SidebarMenuButton
            class="hidden text-violet-600 group-data-[collapsible=icon]:flex dark:text-violet-400"
            :tooltip="t('Back to my account')" @click="exitImpersonation">
            <Eye />
          </SidebarMenuButton>
        </SidebarMenuItem>

        <SidebarMenuItem>
          <DropdownMenu>
            <DropdownMenuTrigger as-child>
              <SidebarMenuButton size="lg" class="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground" :tooltip="auth.user?.full_name">
                <SidebarUser />
                <ChevronsUpDown class="ml-auto" />
              </SidebarMenuButton>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              class="w-(--reka-dropdown-menu-trigger-width) min-w-56 rounded-lg"
              :side="isMobile ? 'bottom' : 'right'" align="end" :side-offset="4"
            >
              <DropdownMenuItem class="p-0 font-normal focus:bg-sidebar-accent" :title="t('Open my profile')" @click="goToProfile">
                <div class="flex w-full items-center gap-2 px-1 py-1.5 text-left">
                  <SidebarUser />
                </div>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuLabel class="text-xs text-muted-foreground">{{ t('Theme') }}</DropdownMenuLabel>
              <DropdownMenuRadioGroup :model-value="colorMode.currentTheme.value" @update:model-value="onThemeChange">
                <DropdownMenuRadioItem value="light" class="gap-2 p-2">
                  <Sun class="size-4 shrink-0" />
                  <span>{{ t('Light') }}</span>
                </DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="dark" class="gap-2 p-2">
                  <Moon class="size-4 shrink-0" />
                  <span>{{ t('Dark') }}</span>
                </DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="system" class="gap-2 p-2">
                  <Monitor class="size-4 shrink-0" />
                  <span>{{ t('System') }}</span>
                </DropdownMenuRadioItem>
              </DropdownMenuRadioGroup>
              <DropdownMenuSeparator />
              <DropdownMenuLabel class="text-xs text-muted-foreground">{{ t('Language') }}</DropdownMenuLabel>
              <DropdownMenuRadioGroup :model-value="currentLanguage" @update:model-value="onLanguageChange">
                <DropdownMenuRadioItem v-for="lang in languages" :key="lang.code" :value="lang.code" class="gap-2 p-2">
                  <Languages class="size-4 shrink-0" />
                  <span>{{ lang.name }}</span>
                </DropdownMenuRadioItem>
              </DropdownMenuRadioGroup>
              <DropdownMenuSeparator />
              <DropdownMenuItem class="gap-2 p-2" :title="t('Reload translations, menus and schemas; your settings and drafts are kept')" @click="clearClientCache">
                <RefreshCw class="size-4 shrink-0" />
                <span>{{ t('Clear cache') }}</span>
              </DropdownMenuItem>
              <DropdownMenuItem class="gap-2 p-2" @click="handleLogout">
                <LogOut class="size-4 shrink-0" />
                <span>{{ t('Log out') }}</span>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </SidebarMenuItem>
      </SidebarMenu>
    </SidebarFooter>

    <SidebarRail />
  </Sidebar>
</template>
