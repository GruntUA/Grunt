<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useWorkspaceStore } from '@/stores/workspace'
import WorkspaceSidebar from '@/components/workspace/WorkspaceSidebar.vue'
import MobileBottomNav from '@/components/mobile/MobileBottomNav.vue'
import { Menu } from '@lucide/vue'

const props = defineProps<{ workspaceName: string }>()
const wsStore = useWorkspaceStore()
const route = useRoute()

const sidebarRef = ref<InstanceType<typeof WorkspaceSidebar> | null>(null)
const contentKey = ref(0)

async function loadWorkspace(name: string) {
  await wsStore.setActive(name)
  contentKey.value++
}

onMounted(() => loadWorkspace(props.workspaceName))

watch(() => props.workspaceName, (name) => {
  loadWorkspace(name)
})
</script>

<template>
  <div class="flex h-screen overflow-hidden bg-background relative">
    <!-- Sophisticated background pattern -->
    <div class="absolute inset-0 pointer-events-none opacity-[0.03] dark:opacity-[0.05] z-0">
      <svg class="h-full w-full" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse">
            <path d="M 32 0 L 0 0 0 32" fill="none" stroke="currentColor" stroke-width="1"/>
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#grid)" />
      </svg>
    </div>
    
    <!-- Subtle color blobs for depth -->
    <div class="absolute -top-[10%] -left-[10%] w-[40%] h-[40%] bg-primary/5 rounded-full blur-[120px] pointer-events-none" />
    <div class="absolute -bottom-[10%] -right-[10%] w-[40%] h-[40%] bg-primary/5 rounded-full blur-[120px] pointer-events-none" />

    <!-- Mobile hamburger -->
    <button class="fixed top-4 left-4 z-30 p-2.5 rounded-xl bg-card border border-border shadow-lg md:hidden hover:bg-accent transition-colors"
      @click="sidebarRef && (sidebarRef.mobileOpen = true)">
      <Menu class="size-5" />
    </button>

    <WorkspaceSidebar ref="sidebarRef" :workspace-name="workspaceName" class="relative z-10" />

    <!-- Main content — extra bottom padding on mobile for the nav bar -->
    <main class="flex-1 overflow-y-auto pb-14 md:pb-0 relative z-10 bg-background/40 backdrop-blur-[2px]">
      <RouterView v-slot="{ Component }" :key="route.fullPath">
        <Transition name="fade" mode="out-in">
          <component :is="Component" />
        </Transition>
      </RouterView>
    </main>

    <MobileBottomNav :workspace-name="workspaceName" />
  </div>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 150ms ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
