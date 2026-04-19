<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useWorkspaceStore } from '@/stores/workspace'
import WorkspaceSidebar from '@/components/workspace/WorkspaceSidebar.vue'
import MobileBottomNav from '@/components/mobile/MobileBottomNav.vue'
import { SidebarProvider, SidebarInset } from '@/components/ui/sidebar'

const props = defineProps<{ workspaceName: string }>()
const wsStore = useWorkspaceStore()
const route = useRoute()
const contentKey = ref(0)

async function loadWorkspace(name: string) {
  await wsStore.setActive(name)
  contentKey.value++
}

onMounted(() => loadWorkspace(props.workspaceName))
watch(() => props.workspaceName, (name) => { loadWorkspace(name) })
</script>

<template>
  <SidebarProvider class="h-screen overflow-hidden bg-background">
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

    <WorkspaceSidebar :workspace-name="workspaceName" />

    <SidebarInset class="overflow-y-auto pb-14 md:pb-0 relative z-10 bg-background/40 backdrop-blur-[2px]">
      <RouterView v-slot="{ Component }" :key="route.fullPath">
        <Transition name="fade" mode="out-in">
          <component :is="Component" />
        </Transition>
      </RouterView>
    </SidebarInset>

    <MobileBottomNav :workspace-name="workspaceName" />
  </SidebarProvider>
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
