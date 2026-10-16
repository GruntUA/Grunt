<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ChevronRight } from '@lucide/vue'
import type { WorkspaceLink } from '@/core/api/workspace'
import { isLinkActive } from '@/core/workspaceUrl'
import AppIcon from '@/components/AppIcon.vue'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem, useSidebar } from '@/components/ui/sidebar'
import SidebarItem from './SidebarItem.vue'

// One sidebar section shown as a module (AppMenu sidebar_mode "modules"): a row
// with the section's icon whose items open in a panel beside the sidebar. On
// mobile the sidebar is a sheet - the parent drills into the module instead.
const props = defineProps<{
  section: string
  icon: string
  items: WorkspaceLink[]
  workspaceName: string
}>()

const emit = defineEmits<{ drill: [] }>()

const route = useRoute()
const { isMobile } = useSidebar()

const open = ref(false)
const active = computed(() => props.items.some((item) => isLinkActive(item, route.params)))

// Picking an item navigates - the panel has done its job.
watch(() => route.fullPath, () => { open.value = false })
</script>

<template>
  <SidebarMenuItem>
    <SidebarMenuButton v-if="isMobile" :is-active="active" @click="emit('drill')">
      <AppIcon :icon="icon || 'folder'" />
      <span>{{ section }}</span>
      <ChevronRight class="ml-auto" />
    </SidebarMenuButton>

    <Popover v-else v-model:open="open">
      <PopoverTrigger as-child>
        <SidebarMenuButton :is-active="active" :tooltip="section" class="data-[state=open]:bg-sidebar-accent">
          <AppIcon :icon="icon || 'folder'" />
          <span>{{ section }}</span>
          <ChevronRight class="ml-auto" />
        </SidebarMenuButton>
      </PopoverTrigger>
      <PopoverContent side="right" align="start" :side-offset="8" class="w-64 p-2">
        <p class="px-2 pb-1.5 text-xs font-medium text-muted-foreground">{{ section }}</p>
        <SidebarMenu>
          <SidebarItem
            v-for="item in items" :key="item.link_to + item.sequence" :item="item" flyout :workspace-name="workspaceName"
          />
        </SidebarMenu>
      </PopoverContent>
    </Popover>
  </SidebarMenuItem>
</template>
