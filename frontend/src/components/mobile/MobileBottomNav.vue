<script setup lang="ts">
/**
 * MobileBottomNav — fixed bottom navigation bar for small screens.
 *
 * Shows up to 4 top-level workspace items + a "More" overflow sheet.
 * Visible only on mobile (hidden on md+) so it does not interfere with
 * the desktop sidebar.
 */
import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAppStore } from '@/stores/app'
import AppIcon from '@/components/AppIcon.vue'
import { MoreHorizontal, Home } from '@lucide/vue'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'

const props = defineProps<{ workspaceName: string }>()

const router = useRouter()
const route = useRoute()
const appStore = useAppStore()

// ── Derive nav items from active workspace ─────────────────────────────────

const navItems = computed(() => {
  return appStore.groupedItems
    .flatMap(g => g.items)
    .filter(i => i.type === 'DocType' || i.type === 'Report')
    .slice(0, 4)
})

const overflowItems = computed(() => {
  return appStore.groupedItems
    .flatMap(g => g.items)
    .filter(i => i.type === 'DocType' || i.type === 'Report')
    .slice(4)
})

const showOverflow = ref(false)

// ── Route helpers ──────────────────────────────────────────────────────────

function isActive(link_to: string) {
  return route.params.doctype === link_to
}

function navigate(item: { type: string; link_to: string }) {
  showOverflow.value = false
  if (item.type === 'DocType') {
    router.push(`/${props.workspaceName}/${item.link_to}`)
  } else if (item.type === 'Report') {
    router.push(`/${props.workspaceName}/report/${item.link_to}`)
  }
}

function goHome() {
  router.push('/')
}
</script>

<template>
  <!-- Only visible on mobile -->
  <nav
    class="md:hidden fixed bottom-0 inset-x-0 z-40 bg-card/95 border-t border-border/60 safe-b"
    style="padding-bottom: env(safe-area-inset-bottom)"
  >
    <div class="flex items-stretch h-14">
      <!-- Home -->
      <button
        class="flex-1 flex flex-col items-center justify-center gap-0.5 text-muted-foreground transition-colors"
        :class="route.path === '/' ? 'text-primary' : 'hover:text-foreground'"
        @click="goHome"
      >
        <Home class="w-5 h-5" />
        <span class="text-xs font-medium leading-none">Головна</span>
      </button>

      <!-- Top workspace items -->
      <button
        v-for="item in navItems"
        :key="item.link_to"
        class="flex-1 flex flex-col items-center justify-center gap-0.5 transition-colors"
        :class="isActive(item.link_to) ? 'text-primary' : 'text-muted-foreground hover:text-foreground'"
        @click="navigate(item)"
      >
        <AppIcon :icon="item.icon || 'file'" class="size-5" />
        <span class="text-xs font-medium leading-none truncate max-w-[52px]">{{ item.label }}</span>
      </button>

      <!-- More button (when overflow items exist) -->
      <button
        v-if="overflowItems.length > 0"
        class="flex-1 flex flex-col items-center justify-center gap-0.5 text-muted-foreground hover:text-foreground transition-colors"
        @click="showOverflow = true"
      >
        <MoreHorizontal class="w-5 h-5" />
        <span class="text-xs font-medium leading-none">Ще</span>
      </button>
    </div>
  </nav>

  <!-- Overflow sheet -->
  <Sheet :open="showOverflow" @update:open="(v: boolean) => (showOverflow = v)">
    <SheetContent side="bottom" class="md:hidden p-0 rounded-t-lg" style="padding-bottom: env(safe-area-inset-bottom)">
      <SheetHeader class="flex-row items-center justify-between px-5 pt-4 pb-2 gap-0 space-y-0">
        <SheetTitle>Всі розділи</SheetTitle>
      </SheetHeader>
      <div class="max-h-72 overflow-y-auto">
        <div class="px-3 pb-4 space-y-0.5">
          <button
            v-for="item in overflowItems"
            :key="item.link_to"
            class="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors"
            :class="isActive(item.link_to)
              ? 'bg-primary/10 text-primary font-medium'
              : 'text-foreground hover:bg-muted'"
            @click="navigate(item)"
          >
            <AppIcon :icon="item.icon || 'file'" class="size-5 shrink-0 opacity-80" />
            <span class="flex-1 text-left truncate">{{ item.label }}</span>
          </button>
        </div>
      </div>
    </SheetContent>
  </Sheet>
</template>
