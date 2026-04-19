<script setup lang="ts">
import type { Component } from 'vue'
import { DotsHorizontalIcon } from '@radix-icons/vue'
import { ArrowUpRight, Link, StarOff } from '@lucide/vue'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from '@/components/ui/sidebar'
import AppIcon from '@/components/AppIcon.vue'

interface FavoriteItem {
  name: string
  url: string
  icon: string | Component
}

const emit = defineEmits<{
  (e: 'unpin', item: FavoriteItem): void
}>()

defineProps<{ favorites: FavoriteItem[] }>()

const { isMobile } = useSidebar()

function copyLink(url: string) {
  window.navigator.clipboard.writeText(url)
}

function openInNewTab(url: string) {
  window.open(url, '_blank')
}
</script>

<template>
  <SidebarGroup class="group-data-[collapsible=icon]:hidden">
    <SidebarGroupLabel>Закріплені</SidebarGroupLabel>
    <SidebarMenu>
      <SidebarMenuItem v-for="item in favorites" :key="item.name">
        <RouterLink :to="item.url" custom v-slot="{ isActive, href, navigate }">
          <SidebarMenuButton as="a" :href="href" :title="item.name" :is-active="isActive" @click="navigate">
            <AppIcon :icon="item.icon" class="size-4 shrink-0" />
            <span>{{ item.name }}</span>
          </SidebarMenuButton>
        </RouterLink>
        <DropdownMenu>
          <DropdownMenuTrigger as-child>
            <SidebarMenuAction show-on-hover>
              <DotsHorizontalIcon />
              <span class="sr-only">Дії</span>
            </SidebarMenuAction>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            class="w-56 rounded-lg"
            :side="isMobile ? 'bottom' : 'right'"
            :align="isMobile ? 'end' : 'start'"
          >
            <DropdownMenuItem @click="emit('unpin', item)">
              <StarOff class="text-muted-foreground" />
              <span>Відкріпити</span>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem @click="copyLink(item.url)">
              <Link class="text-muted-foreground" />
              <span>Копіювати посилання</span>
            </DropdownMenuItem>
            <DropdownMenuItem @click="openInNewTab(item.url)">
              <ArrowUpRight class="text-muted-foreground" />
              <span>Відкрити в новій вкладці</span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>

      <SidebarMenuItem>
        <SidebarMenuButton class="text-sidebar-foreground/70">
          <DotsHorizontalIcon />
          <span>Більше</span>
        </SidebarMenuButton>
      </SidebarMenuItem>
    </SidebarMenu>
  </SidebarGroup>
</template>
