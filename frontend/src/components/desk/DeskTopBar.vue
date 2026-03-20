<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const showUserMenu = ref(false)

function logout() {
  auth.logout()
  router.push('/login')
}

function initials(name: string): string {
  return name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
}
</script>

<template>
  <header class="h-[--grunt-topbar-h] flex items-center justify-between px-6 bg-[--grunt-surface] border-b border-[--grunt-border]">
    <router-link to="/" class="text-lg font-bold text-[--grunt-primary]">
      Ґрунт
    </router-link>

    <div class="flex items-center gap-3">
      <!-- Notifications placeholder -->
      <button class="p-2 rounded-[--grunt-radius-sm] text-[--grunt-text-secondary] hover:bg-[--grunt-surface-secondary] transition-colors" title="Сповіщення">
        🔔
      </button>

      <!-- User menu -->
      <div class="relative">
        <button
          class="flex items-center gap-2 px-2 py-1.5 rounded-[--grunt-radius-sm] hover:bg-[--grunt-surface-secondary] transition-colors"
          @click="showUserMenu = !showUserMenu"
        >
          <span class="w-8 h-8 rounded-full bg-[--grunt-primary] text-white text-xs font-medium flex items-center justify-center">
            {{ auth.user ? initials(auth.user.full_name) : '?' }}
          </span>
          <span class="text-sm text-[--grunt-text-primary] hidden sm:inline">{{ auth.user?.full_name }}</span>
        </button>

        <div
          v-if="showUserMenu"
          class="absolute right-0 top-full mt-1 bg-[--grunt-surface] border border-[--grunt-border] rounded-[--grunt-radius-md] shadow-[--grunt-shadow-md] z-50 min-w-40 py-1"
          @click="showUserMenu = false"
        >
          <div class="px-3 py-2 text-xs text-[--grunt-text-muted] border-b border-[--grunt-border]">
            {{ auth.user?.email }}
          </div>
          <router-link
            v-if="auth.user?.is_superadmin"
            to="/studio"
            class="flex items-center gap-2 px-3 py-2 text-sm text-[--grunt-text-secondary] hover:bg-[--grunt-surface-secondary]"
          >
            🔧 Studio
          </router-link>
          <button
            class="w-full flex items-center gap-2 px-3 py-2 text-sm text-[--grunt-text-secondary] hover:bg-[--grunt-surface-secondary] hover:text-[--grunt-danger]"
            @click="logout"
          >
            Вийти
          </button>
        </div>
      </div>
    </div>
  </header>

  <!-- Overlay to close menu -->
  <div v-if="showUserMenu" class="fixed inset-0 z-40" @click="showUserMenu = false" />
</template>
