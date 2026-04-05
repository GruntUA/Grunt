<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useWorkspaceStore } from '@/stores/workspace'
import WorkspaceSidebar from '@/components/workspace/WorkspaceSidebar.vue'
import MobileBottomNav from '@/components/mobile/MobileBottomNav.vue'
import { Menu } from 'lucide-vue-next'

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
  <div class="flex h-screen overflow-hidden bg-background">
    <!-- Mobile hamburger -->
    <button class="fixed top-3 left-3 z-30 p-2 rounded-md bg-card border border-border shadow-sm md:hidden"
      @click="sidebarRef && (sidebarRef.mobileOpen = true)">
      <Menu class="size-4" />
    </button>

    <WorkspaceSidebar ref="sidebarRef" :workspace-name="workspaceName" />

    <!-- Main content — extra bottom padding on mobile for the nav bar -->
    <main class="flex-1 overflow-y-auto pb-14 md:pb-0">
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
