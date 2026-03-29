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
} from 'lucide-vue-next'
import { useColorMode } from '@/core/composables/useColorMode'
import type { Theme } from '@/core/composables/useColorMode'
import SidebarItem from './SidebarItem.vue'

defineProps<{ workspaceName: string }>()

const wsStore = useWorkspaceStore()
const auth = useAuthStore()
const router = useRouter()

const collapsed = ref(false)

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
    <div
      v-if="mobileOpen"
      class="fixed inset-0 bg-black/40 backdrop-blur-sm z-40 md:hidden"
      @click="mobileOpen = false"
    />
  </Transition>

  <TooltipProvider :delay-duration="0">
    <aside
      class="flex flex-col bg-sidebar border-r border-sidebar-border h-screen transition-all duration-200 shrink-0"
      :class="[
        collapsed ? 'w-[52px]' : 'w-[240px]',
        mobileOpen ? 'fixed inset-y-0 left-0 z-50' : 'hidden md:flex'
      ]"
    >
      <!-- Header -->
      <div
        class="flex items-center h-12 shrink-0 border-b border-sidebar-border"
        :class="collapsed ? 'justify-center px-2' : 'px-3 gap-2'"
      >
        <Tooltip v-if="collapsed">
          <TooltipTrigger as-child>
            <button
              class="p-1.5 rounded-md text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
              @click="goToDesk"
            >
              <ArrowLeft class="size-4" />
            </button>
          </TooltipTrigger>
          <TooltipContent side="right">Робочий стіл</TooltipContent>
        </Tooltip>

        <template v-else>
          <button
            class="p-1.5 rounded-md text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
            title="Робочий стіл"
            @click="goToDesk"
          >
            <ArrowLeft class="size-4" />
          </button>
          <template v-if="wsStore.active">
            <span class="text-base leading-none">{{ wsStore.active.icon }}</span>
            <span class="text-sm font-semibold text-foreground truncate">{{ wsStore.active.label }}</span>
          </template>
        </template>
      </div>

      <!-- Navigation -->
      <ScrollArea class="flex-1">
        <nav class="p-2 flex flex-col gap-0.5">
          <template v-for="(group, gi) in wsStore.groupedItems" :key="gi">
            <!-- Divider -->
            <Separator v-if="group.section === '__divider__'" class="my-2" />

            <template v-else>
              <!-- Section label -->
              <p
                v-if="group.section && !collapsed"
                class="px-2.5 pt-4 pb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/70 select-none"
              >{{ group.section }}</p>

              <SidebarItem
                v-for="item in group.items"
                :key="item.link_to + item.sequence"
                :item="item"
                :workspace-name="workspaceName"
                :count="wsStore.counts[item.link_to] ?? wsStore.counts[item.link_to + '_' + (item.count_filters ? Object.values(JSON.parse(item.count_filters || '{}')).join('_').toLowerCase() : '')] ?? 0"
                :collapsed="collapsed"
                :color="wsStore.active?.color"
              />
            </template>
          </template>
        </nav>
      </ScrollArea>

      <!-- Footer -->
      <div class="border-t border-sidebar-border shrink-0 p-2">
        <!-- Collapse toggle (desktop only) -->
        <button
          class="w-full flex items-center justify-center p-1.5 rounded-md text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors mb-1 hidden md:flex"
          :title="collapsed ? 'Розгорнути' : 'Згорнути'"
          @click="toggleCollapse"
        >
          <PanelLeft v-if="collapsed" class="size-4" />
          <PanelLeftClose v-else class="size-4" />
        </button>

        <!-- User menu -->
        <DropdownMenu v-if="!collapsed">
          <DropdownMenuTrigger as-child>
            <button class="w-full flex items-center gap-2 p-1.5 rounded-md hover:bg-accent transition-colors">
              <span class="size-7 rounded-md bg-primary text-primary-foreground text-xs font-medium flex items-center justify-center shrink-0">
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
            <DropdownMenuRadioGroup :model-value="colorMode.currentTheme.value" @update:model-value="(v) => typeof v === 'string' && onThemeChange(v)">
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
              <span class="size-7 rounded-md bg-primary text-primary-foreground text-xs font-medium flex items-center justify-center">
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
