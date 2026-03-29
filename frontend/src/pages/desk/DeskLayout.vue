<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { RouterView, RouterLink, useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useDocTypeStore } from '@/stores/doctype'
import { usePageStore } from '@/stores/pages'
import NotificationBell from '@/components/desk/NotificationBell.vue'
import { Spinner } from '@/components/ui/spinner'
import { BarChart2, LogOut, Sprout, Moon, Sun } from 'lucide-vue-next'
import { useColorMode } from '@/core/composables/useColorMode'

const auth = useAuthStore()
const dtStore = useDocTypeStore()
const pageStore = usePageStore()
const router = useRouter()
const route = useRoute()
const colorMode = useColorMode()

onMounted(() => {
  dtStore.loadAll()
  pageStore.loadAll()
})

const sidebarSections = computed(() => {
  const sections: Record<string, typeof pageStore.pages> = {}
  for (const page of pageStore.pages) {
    const section = page.sidebar_section || 'Додаток'
    if (!sections[section]) sections[section] = []
    sections[section].push(page)
  }
  return sections
})

function logout() {
  auth.logout()
  router.push('/login')
}

function initials(name: string): string {
  return name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
}
</script>

<template>
  <div class="flex h-screen overflow-hidden bg-background">
    <!-- Sidebar -->
    <aside class="w-60 flex-shrink-0 flex flex-col bg-sidebar border-r border-sidebar-border">

      <!-- Logo -->
      <div class="h-14 flex items-center gap-2.5 px-4 border-b border-sidebar-border">
        <div class="w-7 h-7 rounded-lg bg-primary flex items-center justify-center shadow-sm">
          <Sprout class="w-4 h-4 text-primary-foreground" />
        </div>
        <RouterLink to="/" class="text-base font-bold text-foreground tracking-tight">Ґрунт</RouterLink>
      </div>

      <!-- Navigation -->
      <nav class="flex-1 overflow-y-auto py-3 px-2 space-y-0.5">
        <Spinner v-if="dtStore.loading" class="mx-auto mt-4" size="sm" />

        <!-- Reports link -->
        <RouterLink
          to="/reports"
          :class="[
            'flex items-center gap-2.5 px-3 h-9 text-sm rounded-md transition-colors',
            route.path.startsWith('/reports')
              ? 'bg-sidebar-accent text-sidebar-accent-foreground font-medium'
              : 'text-sidebar-foreground/70 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground'
          ]"
        >
          <BarChart2 class="w-4 h-4 flex-shrink-0" />
          Звіти
        </RouterLink>

        <!-- App pages -->
        <template v-for="(pages, section) in sidebarSections" :key="section">
          <div class="pt-3 pb-1">
            <p class="px-3 text-[11px] font-semibold text-sidebar-foreground/40 uppercase tracking-wider">{{ section }}</p>
          </div>
          <RouterLink
            v-for="page in pages"
            :key="page.route"
            :to="page.route"
            :class="[
              'flex items-center gap-2.5 px-3 h-9 text-sm rounded-md transition-colors',
              route.path === page.route
                ? 'bg-sidebar-accent text-sidebar-accent-foreground font-medium'
                : 'text-sidebar-foreground/70 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground'
            ]"
          >
            <span v-if="page.icon" class="flex-shrink-0">{{ page.icon }}</span>
            <span class="truncate">{{ page.title }}</span>
          </RouterLink>
        </template>

        <!-- DocTypes -->
        <template v-if="dtStore.doctypes.length > 0">
          <div class="pt-3 pb-1">
            <p class="px-3 text-[11px] font-semibold text-sidebar-foreground/40 uppercase tracking-wider">Документи</p>
          </div>
          <RouterLink
            v-for="dt in dtStore.doctypes"
            :key="dt.name"
            :to="`/${dt.name}`"
            :class="[
              'flex items-center gap-2.5 px-3 h-9 text-sm rounded-md transition-colors',
              route.params.doctype === dt.name
                ? 'bg-sidebar-accent text-sidebar-accent-foreground font-medium'
                : 'text-sidebar-foreground/70 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground'
            ]"
          >
            <span class="w-1.5 h-1.5 rounded-full bg-current opacity-40 flex-shrink-0" />
            <span class="truncate">{{ dt.label }}</span>
          </RouterLink>
        </template>
      </nav>

      <!-- User footer -->
      <div class="border-t border-sidebar-border px-3 py-2.5 flex items-center gap-2.5">
        <span class="w-7 h-7 rounded-full bg-gradient-to-br from-primary to-emerald-700 text-primary-foreground text-[11px] font-semibold flex items-center justify-center flex-shrink-0">
          {{ auth.user ? initials(auth.user.full_name) : '?' }}
        </span>
        <div class="flex-1 min-w-0">
          <p class="text-xs font-medium text-sidebar-foreground truncate">{{ auth.user?.full_name }}</p>
          <p class="text-[11px] text-sidebar-foreground/50 truncate">{{ auth.user?.email }}</p>
        </div>
        <button
          class="p-1.5 rounded-md text-sidebar-foreground/40 hover:text-sidebar-foreground hover:bg-sidebar-accent/60 transition-colors flex-shrink-0"
          :title="colorMode.isDark.value ? 'Світла тема' : 'Темна тема'"
          @click="colorMode.toggle()"
        >
          <Sun v-if="colorMode.isDark.value" class="w-3.5 h-3.5" />
          <Moon v-else class="w-3.5 h-3.5" />
        </button>
        <NotificationBell />
        <button
          class="p-1.5 rounded-md text-sidebar-foreground/40 hover:text-destructive hover:bg-destructive/10 transition-colors flex-shrink-0"
          title="Вийти"
          @click="logout"
        >
          <LogOut class="w-3.5 h-3.5" />
        </button>
      </div>
    </aside>

    <!-- Main content -->
    <main class="flex-1 overflow-y-auto">
      <RouterView :key="route.fullPath" />
    </main>
  </div>
</template>
