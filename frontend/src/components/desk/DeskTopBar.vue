<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { Bell, LogOut, Sprout } from 'lucide-vue-next'

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
  <header class="sticky top-0 z-30 h-14 flex items-center justify-between px-6 bg-card/80 backdrop-blur-lg border-b border-border/60">
    <router-link to="/" class="flex items-center gap-2 group">
      <div class="w-8 h-8 rounded-lg bg-primary text-primary-foreground flex items-center justify-center shadow-sm group-hover:shadow-md transition-shadow">
        <Sprout class="w-4.5 h-4.5" />
      </div>
      <span class="text-lg font-bold text-foreground tracking-tight">Ґрунт</span>
    </router-link>

    <div class="flex items-center gap-1">
      <!-- Notifications -->
      <button
        class="relative p-2.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
        title="Сповіщення"
      >
        <Bell class="w-[18px] h-[18px]" />
      </button>

      <!-- User menu -->
      <div class="relative ml-1">
        <button
          class="flex items-center gap-2.5 pl-2 pr-3 py-1.5 rounded-lg hover:bg-muted transition-colors"
          @click="showUserMenu = !showUserMenu"
        >
          <span class="w-8 h-8 rounded-full bg-gradient-to-br from-primary to-emerald-700 text-primary-foreground text-xs font-semibold flex items-center justify-center shadow-sm">
            {{ auth.user ? initials(auth.user.full_name) : '?' }}
          </span>
          <span class="text-sm font-medium text-foreground hidden sm:inline">{{ auth.user?.full_name }}</span>
        </button>

        <Transition
          enter-active-class="transition duration-150 ease-out"
          enter-from-class="opacity-0 scale-95 -translate-y-1"
          enter-to-class="opacity-100 scale-100 translate-y-0"
          leave-active-class="transition duration-100 ease-in"
          leave-from-class="opacity-100 scale-100"
          leave-to-class="opacity-0 scale-95"
        >
          <div
            v-if="showUserMenu"
            class="absolute right-0 top-full mt-2 bg-card border border-border/60 rounded-xl shadow-xl shadow-black/[0.08] z-50 min-w-48 py-1 overflow-hidden"
            @click="showUserMenu = false"
          >
            <div class="px-4 py-2.5 border-b border-border">
              <p class="text-sm font-medium text-foreground">{{ auth.user?.full_name }}</p>
              <p class="text-xs text-muted-foreground mt-0.5">{{ auth.user?.email }}</p>
            </div>
            <div class="py-1">
              <button
                class="w-full flex items-center gap-2.5 px-4 py-2 text-sm text-muted-foreground hover:text-destructive hover:bg-destructive/5 transition-colors"
                @click="logout"
              >
                <LogOut class="w-4 h-4" />
                Вийти
              </button>
            </div>
          </div>
        </Transition>
      </div>
    </div>
  </header>

  <!-- Overlay to close menu -->
  <div v-if="showUserMenu" class="fixed inset-0 z-20" @click="showUserMenu = false" />
</template>
