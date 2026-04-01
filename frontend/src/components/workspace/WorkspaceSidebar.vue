<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useWorkspaceStore } from '@/stores/workspace'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
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

onMounted(() => {
  const saved = localStorage.getItem('grunt_sidebar_collapsed')
  if (saved === 'true') collapsed.value = true
  if (window.innerWidth >= 768 && window.innerWidth <= 1024) {
    collapsed.value = true
  }
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
              @click="router.push(`/${ws.name}/desk`)">
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


      <!-- Navigation -->
      <ScrollArea class="flex-1">
        <nav class="p-2 flex flex-col gap-0.5">
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

          <div v-if="!collapsed && auth.user?.is_superadmin" class="px-2 pt-6">
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
