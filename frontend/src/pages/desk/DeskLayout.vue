<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { RouterView, RouterLink, useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useDocTypeStore } from '@/stores/doctype'
import { usePageStore } from '@/stores/pages'
import GSpinner from '@/components/ui/GSpinner.vue'

const auth = useAuthStore()
const dtStore = useDocTypeStore()
const pageStore = usePageStore()
const router = useRouter()
const route = useRoute()

onMounted(() => {
  dtStore.loadAll()
  pageStore.loadAll()
})

// Group app pages by sidebar_section
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
</script>

<template>
  <div class="flex h-screen overflow-hidden bg-[--grunt-surface-secondary]">
    <!-- Sidebar -->
    <aside class="w-60 flex-shrink-0 flex flex-col bg-[--grunt-surface] border-r border-[--grunt-border]">
      <!-- Logo -->
      <div class="h-14 flex items-center px-5 border-b border-[--grunt-border]">
        <RouterLink to="/" class="text-lg font-bold text-[--grunt-primary]">Ґрунт</RouterLink>
      </div>

      <!-- DocType nav -->
      <nav class="flex-1 overflow-y-auto py-3 px-2">
        <GSpinner v-if="dtStore.loading" class="mx-auto mt-4" size="sm" />

        <!-- Reports link -->
        <RouterLink
          to="/reports"
          :class="[
            'flex items-center gap-2 px-3 py-2 text-sm rounded-[--grunt-radius-sm] mb-1 transition-colors',
            route.path.startsWith('/reports')
              ? 'bg-[--grunt-primary-light] text-[--grunt-primary] font-medium'
              : 'text-[--grunt-text-secondary] hover:bg-[--grunt-surface-secondary]'
          ]"
        >
          <span>📊</span> Звіти
        </RouterLink>

        <!-- App pages (dynamic from installed apps) -->
        <template v-for="(pages, section) in sidebarSections" :key="section">
          <hr class="border-[--grunt-border] my-2" />
          <p class="px-3 py-1 text-xs font-semibold text-[--grunt-text-muted] uppercase tracking-wider">{{ section }}</p>
          <RouterLink
            v-for="page in pages"
            :key="page.route"
            :to="page.route"
            :class="[
              'flex items-center gap-2 px-3 py-2 text-sm rounded-[--grunt-radius-sm] mb-0.5 transition-colors',
              route.path === page.route
                ? 'bg-[--grunt-primary-light] text-[--grunt-primary] font-medium'
                : 'text-[--grunt-text-secondary] hover:bg-[--grunt-surface-secondary]'
            ]"
          >
            <span v-if="page.icon">{{ page.icon }}</span>
            {{ page.title }}
          </RouterLink>
        </template>

        <hr class="border-[--grunt-border] my-2" />

        <RouterLink
          v-for="dt in dtStore.doctypes"
          :key="dt.name"
          :to="`/${dt.name}`"
          :class="[
            'flex items-center px-3 py-2 text-sm rounded-[--grunt-radius-sm] mb-0.5 transition-colors',
            route.params.doctype === dt.name
              ? 'bg-[--grunt-primary-light] text-[--grunt-primary] font-medium'
              : 'text-[--grunt-text-secondary] hover:bg-[--grunt-surface-secondary]'
          ]"
        >
          {{ dt.label }}
        </RouterLink>
      </nav>

      <!-- App Studio links (superadmin only) -->
      <div v-if="auth.user?.is_superadmin" class="px-2 pb-2 flex flex-col gap-0.5 border-t border-[--grunt-border] pt-2">
        <RouterLink
          to="/studio"
          class="flex items-center gap-2 px-3 py-2 text-sm rounded-[--grunt-radius-sm] text-[--grunt-text-secondary] hover:bg-[--grunt-surface-secondary] transition-colors"
        >
          <span>🔧</span> App Studio
        </RouterLink>
        <RouterLink
          to="/studio/users"
          class="flex items-center gap-2 px-3 py-2 text-sm rounded-[--grunt-radius-sm] text-[--grunt-text-secondary] hover:bg-[--grunt-surface-secondary] transition-colors"
        >
          <span>👥</span> Користувачі
        </RouterLink>
        <RouterLink
          to="/studio/roles"
          class="flex items-center gap-2 px-3 py-2 text-sm rounded-[--grunt-radius-sm] text-[--grunt-text-secondary] hover:bg-[--grunt-surface-secondary] transition-colors"
        >
          <span>🔐</span> Ролі
        </RouterLink>
      </div>

      <!-- User info + logout -->
      <div class="border-t border-[--grunt-border] px-4 py-3">
        <p class="text-xs text-[--grunt-text-muted] truncate">{{ auth.user?.full_name ?? auth.user?.email }}</p>
        <button class="mt-1 text-xs text-[--grunt-text-secondary] hover:text-[--grunt-danger] transition-colors" @click="logout">
          Вийти
        </button>
      </div>
    </aside>

    <!-- Main -->
    <main class="flex-1 overflow-y-auto">
      <RouterView :key="route.fullPath" />
    </main>
  </div>
</template>
