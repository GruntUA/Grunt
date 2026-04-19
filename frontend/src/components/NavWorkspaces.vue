<script setup lang="ts">
import { ref } from 'vue'
import { ChevronRight, MoreHorizontal } from '@lucide/vue'
import AppIcon from '@/components/AppIcon.vue'
import {
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
} from '@/components/ui/sidebar'

interface WorkspacePage {
  name: string
  icon: string
  url?: string
}

interface WorkspaceGroup {
  name: string
  icon: string
  pages: WorkspacePage[]
}

defineProps<{ workspaces: WorkspaceGroup[] }>()

const expanded = ref<Record<string, boolean>>({})

function toggle(key: string) {
  expanded.value[key] = !expanded.value[key]
}
</script>

<template>
  <SidebarGroup>
    <SidebarGroupLabel>Простори</SidebarGroupLabel>

    <div v-for="ws in workspaces" :key="ws.name" class="flex flex-col">
      <!-- Workspace header -->
      <button
        type="button"
        class="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm font-medium text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
        @click="toggle(ws.name)"
      >
        <AppIcon :icon="ws.icon" class="size-4 shrink-0" />
        <span class="flex-1 text-left truncate">{{ ws.name }}</span>
        <ChevronRight
          v-if="ws.pages.length"
          class="size-3.5 text-muted-foreground transition-transform duration-200"
          :style="{ transform: expanded[ws.name] ? 'rotate(90deg)' : 'none' }"
        />
      </button>

      <!-- Sub-pages -->
      <div v-show="expanded[ws.name]" class="flex flex-col">
        <router-link
          v-for="page in ws.pages"
          :key="page.url ?? page.name"
          v-slot="rp"
          :to="page.url ?? '/'"
          custom
        >
          <a
            :href="rp.href"
            class="flex h-7 items-center gap-2 rounded-md pl-6 pr-2 text-sm text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
            :class="rp.isActive ? 'bg-sidebar-accent font-medium' : ''"
            @click="rp.navigate"
          >
            <AppIcon :icon="page.icon" class="size-3.5 shrink-0" />
            <span class="truncate">{{ page.name }}</span>
          </a>
        </router-link>
      </div>
    </div>

    <SidebarMenu class="mt-0.5">
      <SidebarMenuItem>
        <SidebarMenuButton class="text-sidebar-foreground/70">
          <MoreHorizontal class="size-4" />
          <span>Більше</span>
        </SidebarMenuButton>
      </SidebarMenuItem>
    </SidebarMenu>
  </SidebarGroup>
</template>
