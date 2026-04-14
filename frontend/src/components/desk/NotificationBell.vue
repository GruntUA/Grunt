<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useNotifications } from '@/core/composables/useNotifications'
import { Bell, CheckCheck } from '@lucide/vue'

const router = useRouter()
const { notifications, unreadCount, loading, markRead, markAllRead } = useNotifications()
const open = ref(false)

function toggle() {
  open.value = !open.value
}

function close() {
  open.value = false
}

async function onClickNotification(n: typeof notifications.value[number]) {
  if (!n.is_read) await markRead(n.id)
  if (n.doctype && n.doc_id) {
    router.push(`/${n.doctype}/${n.doc_id}`)
    close()
  }
}

async function onMarkAllRead() {
  await markAllRead()
}

function timeAgo(iso: string | null): string {
  if (!iso) return ''
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1) return 'щойно'
  if (m < 60) return `${m} хв`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h} год`
  return `${Math.floor(h / 24)} дн`
}
</script>

<template>
  <div class="relative">
    <button
      class="relative p-2.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
      title="Сповіщення" @click="toggle">
      <Bell class="w-[18px] h-[18px]" />
      <span v-if="unreadCount > 0"
        class="absolute top-1.5 right-1.5 min-w-[16px] h-4 px-1 rounded-full bg-destructive text-destructive-foreground text-[10px] font-bold flex items-center justify-center leading-none">
        {{ unreadCount > 99 ? '99+' : unreadCount }}
      </span>
    </button>

    <!-- Dropdown -->
    <Transition enter-active-class="transition duration-150 ease-out"
      enter-from-class="opacity-0 scale-95 -translate-y-1" enter-to-class="opacity-100 scale-100 translate-y-0"
      leave-active-class="transition duration-100 ease-in" leave-from-class="opacity-100 scale-100"
      leave-to-class="opacity-0 scale-95">
      <div v-if="open"
        class="absolute right-0 top-full mt-2 w-80 bg-card border border-border/60 rounded-xl shadow-xl shadow-black/[0.08] z-50 overflow-hidden">
        <!-- Header -->
        <div class="flex items-center justify-between px-4 py-3 border-b border-border">
          <h3 class="text-sm font-semibold text-foreground">Сповіщення</h3>
          <button v-if="unreadCount > 0"
            class="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
            @click="onMarkAllRead">
            <CheckCheck class="w-3.5 h-3.5" />
            Прочитати всі
          </button>
        </div>

        <!-- List -->
        <div class="max-h-80 overflow-y-auto">
          <div v-if="loading && notifications.length === 0" class="px-4 py-8 text-center text-sm text-muted-foreground">
            Завантаження...
          </div>

          <div v-else-if="notifications.length === 0" class="px-4 py-8 text-center text-sm text-muted-foreground">
            Немає сповіщень
          </div>

          <div v-for="n in notifications" :key="n.id"
            class="flex gap-3 px-4 py-3 border-b border-border/50 last:border-0 cursor-pointer transition-colors"
            :class="n.is_read ? 'hover:bg-muted/40' : 'bg-primary/[0.03] hover:bg-primary/[0.06]'"
            @click="onClickNotification(n)">
            <!-- Unread dot -->
            <div class="flex-shrink-0 pt-1.5">
              <span class="block w-2 h-2 rounded-full" :class="n.is_read ? 'bg-transparent' : 'bg-primary'" />
            </div>

            <div class="flex-1 min-w-0">
              <p class="text-sm text-foreground leading-snug" :class="{ 'font-medium': !n.is_read }">
                {{ n.subject }}
              </p>
              <p v-if="n.message && n.message !== n.subject" class="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                {{ n.message }}
              </p>
              <p class="text-[11px] text-muted-foreground/60 mt-1 tabular-nums">
                {{ timeAgo(n.created_at) }}
              </p>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </div>

  <!-- Overlay to close -->
  <div v-if="open" class="fixed inset-0 z-40" @click="close" />
</template>
