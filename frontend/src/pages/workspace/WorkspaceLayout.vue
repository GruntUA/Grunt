<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useWorkspaceStore } from '@/stores/workspace'
import { useSidebarStore } from '@/stores/sidebar'
import WorkspaceSidebar from '@/components/workspace/WorkspaceSidebar.vue'
import MobileBottomNav from '@/components/mobile/MobileBottomNav.vue'
import NotFound from '@/pages/errors/NotFound.vue'

const props = defineProps<{ workspaceName: string }>()
const wsStore = useWorkspaceStore()
const sidebarStore = useSidebarStore()
const route = useRoute()
const contentKey = ref(0)
const notFound = ref(false)

async function loadWorkspace(name: string) {
  notFound.value = false
  await wsStore.setActive(name)
  if (!wsStore.active) {
    notFound.value = true
    return
  }
  contentKey.value++
}

onMounted(() => loadWorkspace(props.workspaceName))
watch(() => props.workspaceName, (name) => { loadWorkspace(name) })
</script>

<template>
  <NotFound v-if="notFound" />
  <div v-else class="h-screen overflow-hidden bg-background flex relative">
    <!-- Background pattern -->
    <div class="absolute inset-0 pointer-events-none opacity-[0.03] dark:opacity-[0.05] z-0">
      <svg class="h-full w-full" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse">
            <path d="M 32 0 L 0 0 0 32" fill="none" stroke="currentColor" stroke-width="1" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#grid)" />
      </svg>
    </div>
    <div class="absolute -top-[10%] -left-[10%] w-[40%] h-[40%] bg-primary/5 rounded-full blur-[120px] pointer-events-none" />
    <div class="absolute -bottom-[10%] -right-[10%] w-[40%] h-[40%] bg-primary/5 rounded-full blur-[120px] pointer-events-none" />

    <!-- Sidebar: Desktop -->
    <div class="hidden md:block h-full shrink-0 transition-all duration-300 overflow-hidden">
      <WorkspaceSidebar :workspace-name="workspaceName" />
    </div>

    <!-- Sidebar: Mobile (Drawer) -->
    <Drawer
      v-model:visible="sidebarStore.isMobileVisible"
      position="left"
      class="!w-[280px] !p-0"
      :showCloseIcon="false"
      :pt="{
        content: { class: '!p-0' },
        header: { class: '!p-0' }
      }"
    >
      <div class="h-full w-full">
        <WorkspaceSidebar :workspace-name="workspaceName" />
      </div>
    </Drawer>

    <!-- Main Content -->
    <main
      class="flex-1 flex flex-col min-w-0 relative z-10 bg-background/40 backdrop-blur-[2px] transition-all duration-300 overflow-hidden"
    >
      <div class="flex-1 overflow-y-auto pb-14 md:pb-0">
        <RouterView v-slot="{ Component }" :key="route.fullPath">
          <Transition name="fade" mode="out-in">
            <component :is="Component" />
          </Transition>
        </RouterView>
      </div>
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
