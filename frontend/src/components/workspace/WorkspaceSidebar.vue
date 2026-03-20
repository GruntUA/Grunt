<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useWorkspaceStore } from '@/stores/workspace'
import SidebarItem from './SidebarItem.vue'

defineProps<{ workspaceName: string }>()

const wsStore = useWorkspaceStore()
const auth = useAuthStore()
const router = useRouter()

const collapsed = ref(false)

onMounted(() => {
  const saved = localStorage.getItem('grunt_sidebar_collapsed')
  if (saved === 'true') collapsed.value = true

  // Auto-collapse on medium screens
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

// Mobile overlay
const mobileOpen = ref(false)

defineExpose({ mobileOpen })
</script>

<template>
  <!-- Mobile overlay backdrop -->
  <div
    v-if="mobileOpen"
    class="fixed inset-0 bg-black/30 z-40 md:hidden"
    @click="mobileOpen = false"
  />

  <aside
    class="flex flex-col bg-[--grunt-sidebar-bg] border-r border-[--grunt-sidebar-border] h-screen transition-all duration-200 shrink-0"
    :class="[
      collapsed ? 'w-[--grunt-sidebar-width-collapsed]' : 'w-[--grunt-sidebar-width]',
      mobileOpen ? 'fixed inset-y-0 left-0 z-50' : 'hidden md:flex'
    ]"
  >
    <!-- Top: back + workspace name -->
    <div class="h-[--grunt-topbar-h] flex items-center border-b border-[--grunt-sidebar-border] shrink-0" :class="collapsed ? 'justify-center px-1' : 'px-3 gap-2'">
      <button
        class="p-1.5 rounded-[--grunt-radius-sm] text-[--grunt-text-secondary] hover:bg-[--grunt-surface-secondary] transition-colors text-sm"
        title="Робочий стіл"
        @click="goToDesk"
      >←</button>
      <template v-if="!collapsed && wsStore.active">
        <span class="text-base">{{ wsStore.active.icon }}</span>
        <span class="text-sm font-semibold text-[--grunt-text-primary] truncate">{{ wsStore.active.label }}</span>
      </template>
    </div>

    <!-- Navigation items -->
    <nav class="flex-1 overflow-y-auto py-2" :class="collapsed ? 'px-1' : 'px-1'">
      <TransitionGroup name="sidebar-items">
        <template v-for="(group, gi) in wsStore.groupedItems" :key="gi">
          <!-- Divider -->
          <hr v-if="group.section === '__divider__'" class="border-[--grunt-sidebar-border] my-2 mx-2" />

          <template v-else>
            <!-- Section label -->
            <p
              v-if="group.section && !collapsed"
              class="sidebar-section-label"
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
      </TransitionGroup>
    </nav>

    <!-- Bottom: user + collapse toggle -->
    <div class="border-t border-[--grunt-sidebar-border] shrink-0" :class="collapsed ? 'p-1' : 'px-3 py-2'">
      <!-- Collapse toggle -->
      <button
        class="w-full flex items-center justify-center p-1.5 rounded-[--grunt-radius-sm] text-[--grunt-text-muted] hover:bg-[--grunt-surface-secondary] transition-colors text-xs mb-1 hidden md:flex"
        @click="toggleCollapse"
      >
        {{ collapsed ? '→' : '←' }}
      </button>

      <div v-if="!collapsed" class="flex items-center gap-2 py-1">
        <span class="w-7 h-7 rounded-full bg-[--grunt-primary] text-white text-xs font-medium flex items-center justify-center shrink-0">
          {{ auth.user ? initials(auth.user.full_name) : '?' }}
        </span>
        <span class="text-xs text-[--grunt-text-secondary] truncate flex-1">{{ auth.user?.full_name }}</span>
        <router-link
          v-if="auth.user?.is_superadmin"
          to="/studio"
          class="text-xs text-[--grunt-text-muted] hover:text-[--grunt-primary] transition-colors"
          title="Studio"
        >⚙</router-link>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.sidebar-section-label {
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--grunt-sidebar-section-color);
  padding: 16px 12px 4px;
  user-select: none;
}

.sidebar-items-enter-active {
  transition: opacity 150ms ease, transform 150ms ease;
}
.sidebar-items-enter-from {
  opacity: 0;
  transform: translateX(-8px);
}
</style>
