<script setup lang="ts">
import type { Component } from 'vue'
import { ChevronRightIcon, DotsHorizontalIcon, PlusIcon } from '@radix-icons/vue'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
} from '@/components/ui/sidebar'
import AppIcon from '@/components/AppIcon.vue'

interface WorkspacePage {
  name: string
  icon: string | Component
  url?: string
}

interface WorkspaceGroup {
  name: string
  icon: string | Component
  pages: WorkspacePage[]
}

defineProps<{ workspaces: WorkspaceGroup[] }>()
</script>

<template>
  <SidebarGroup>
    <SidebarGroupLabel>Простори</SidebarGroupLabel>
    <SidebarGroupContent>
      <SidebarMenu>
        <Collapsible v-for="ws in workspaces" :key="ws.name">
          <SidebarMenuItem>
            <SidebarMenuButton as-child>
              <RouterLink :to="ws.pages[0]?.url ?? '#'">
                <AppIcon :icon="ws.icon" class="size-4 shrink-0" />
                <span>{{ ws.name }}</span>
              </RouterLink>
            </SidebarMenuButton>
            <CollapsibleTrigger as-child>
              <SidebarMenuAction
                class="left-2 bg-sidebar-accent text-sidebar-accent-foreground data-[state=open]:rotate-90"
                show-on-hover
              >
                <ChevronRightIcon />
              </SidebarMenuAction>
            </CollapsibleTrigger>
            <SidebarMenuAction show-on-hover>
              <PlusIcon />
            </SidebarMenuAction>
            <CollapsibleContent>
              <SidebarMenuSub>
                <SidebarMenuSubItem v-for="page in ws.pages" :key="page.name">
                  <RouterLink :to="page.url ?? '#'" custom v-slot="{ isActive, href, navigate }">
                    <SidebarMenuSubButton as="a" :href="href" :is-active="isActive" @click="navigate">
                      <AppIcon :icon="page.icon" class="size-4 shrink-0" />
                      <span>{{ page.name }}</span>
                    </SidebarMenuSubButton>
                  </RouterLink>
                </SidebarMenuSubItem>
              </SidebarMenuSub>
            </CollapsibleContent>
          </SidebarMenuItem>
        </Collapsible>

        <SidebarMenuItem>
          <SidebarMenuButton class="text-sidebar-foreground/70">
            <DotsHorizontalIcon />
            <span>Більше</span>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    </SidebarGroupContent>
  </SidebarGroup>
</template>
