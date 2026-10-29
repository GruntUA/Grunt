<script setup lang="ts">
import { useI18n } from 'vue-i18n'
/**
 * MobileBottomNav - fixed bottom navigation bar for small screens.
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
import { Button } from '@/components/ui/button'
import { Drawer, DrawerContent, DrawerHeader, DrawerTitle } from '@/components/ui/drawer'
import { appUrl } from '@/core/workspaceUrl'

const { t } = useI18n()

const props = defineProps<{ workspaceName: string }>()

const router = useRouter()
const route = useRoute()
const appStore = useAppStore()

// Derive nav items from active workspace

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

// Route helpers

function isActive(link_to: string) {
  return route.params.doctype === link_to
}

function navigate(item: { type: string; link_to: string }) {
  showOverflow.value = false
  if (item.type === 'DocType' || item.type === 'Report') {
    router.push(appUrl({ type: item.type, name: item.link_to, workspace: props.workspaceName }))
  }
}

function goHome() {
  router.push('/')
}
</script>

<template>
  <!-- Only visible on mobile -->
  <nav
    class="md:hidden fixed bottom-0 inset-x-0 z-40 bg-card border-t border-border/60 safe-b"
    style="padding-bottom: env(safe-area-inset-bottom)"
  >
    <div class="flex items-stretch h-14">
      <!-- Home -->
      <button
        class="flex-1 min-w-0 flex flex-col items-center justify-center gap-1 text-muted-foreground transition-colors"
        :class="route.path === '/' ? 'text-primary' : 'hover:text-foreground'"
        :aria-current="route.path === '/' ? 'page' : undefined"
        @click="goHome"
      >
        <Home class="w-5 h-5" />
        <span class="text-[11px] font-medium leading-none">{{ t('Home') }}</span>
      </button>

      <!-- Top workspace items -->
      <button
        v-for="item in navItems"
        :key="item.link_to"
        class="flex-1 min-w-0 flex flex-col items-center justify-center gap-1 transition-colors"
        :class="isActive(item.link_to) ? 'text-primary' : 'text-muted-foreground hover:text-foreground'"
        :aria-current="isActive(item.link_to) ? 'page' : undefined"
        @click="navigate(item)"
      >
        <AppIcon :icon="item.icon || 'file'" class="size-5" />
        <span class="text-[11px] font-medium leading-none truncate max-w-full px-0.5">{{ item.label }}</span>
      </button>

      <!-- More button (when overflow items exist) -->
      <button
        v-if="overflowItems.length > 0"
        class="flex-1 min-w-0 flex flex-col items-center justify-center gap-1 text-muted-foreground hover:text-foreground transition-colors"
        @click="showOverflow = true"
      >
        <MoreHorizontal class="w-5 h-5" />
        <span class="text-[11px] font-medium leading-none">{{ t('More') }}</span>
      </button>
    </div>
  </nav>

  <!-- Overflow drawer (swipe down to close) -->
  <Drawer v-model:open="showOverflow">
    <DrawerContent class="md:hidden" style="padding-bottom: env(safe-area-inset-bottom)">
      <DrawerHeader>
        <DrawerTitle>{{ t('All sections') }}</DrawerTitle>
      </DrawerHeader>
      <div class="max-h-72 overflow-y-auto px-3 pb-4">
        <Button
          v-for="item in overflowItems"
          :key="item.link_to"
          :variant="isActive(item.link_to) ? 'secondary' : 'ghost'"
          size="lg"
          class="w-full justify-start"
          :aria-current="isActive(item.link_to) ? 'page' : undefined"
          @click="navigate(item)"
        >
          <AppIcon :icon="item.icon || 'file'" />
          <span class="truncate">{{ item.label }}</span>
        </Button>
      </div>
    </DrawerContent>
  </Drawer>
</template>
