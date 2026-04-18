<script setup lang="ts">
import type { Component } from 'vue'
import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
} from '@/components/ui/sidebar'
import AppIcon from '@/components/AppIcon.vue'

interface NavItem {
  title: string
  url: string
  icon: string | Component
  badge?: string
}

defineProps<{ items: NavItem[] }>()
</script>

<template>
  <SidebarGroup>
    <SidebarGroupContent>
      <SidebarMenu>
        <SidebarMenuItem v-for="item in items" :key="item.title">
          <RouterLink :to="item.url" custom v-slot="{ isActive, href, navigate }">
            <SidebarMenuButton as="a" :href="href" :is-active="isActive" @click="navigate">
              <AppIcon :icon="item.icon" />
              <span>{{ item.title }}</span>
            </SidebarMenuButton>
          </RouterLink>
          <SidebarMenuBadge v-if="item.badge">{{ item.badge }}</SidebarMenuBadge>
        </SidebarMenuItem>
      </SidebarMenu>
    </SidebarGroupContent>
  </SidebarGroup>
</template>
