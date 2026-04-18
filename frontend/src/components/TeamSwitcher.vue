<script setup lang="ts">
import type { Component } from 'vue'
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ChevronDownIcon, PlusIcon } from '@radix-icons/vue'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem } from '@/components/ui/sidebar'
import AppIcon from '@/components/AppIcon.vue'

export interface WorkspaceOption {
  name: string
  icon: string | Component
  url?: string
}

const props = defineProps<{ workspaces: WorkspaceOption[] }>()

const router = useRouter()
const active = ref<WorkspaceOption>(props.workspaces[0] ?? { name: 'Ґрунт', icon: 'sprout' })

function select(ws: WorkspaceOption) {
  active.value = ws
  if (ws.url) router.push(ws.url)
}
</script>

<template>
  <SidebarMenu>
    <SidebarMenuItem>
      <DropdownMenu>
        <DropdownMenuTrigger as-child>
          <SidebarMenuButton class="w-fit px-1.5">
            <div class="flex aspect-square size-5 items-center justify-center rounded-md bg-sidebar-primary text-sidebar-primary-foreground text-sm">
              <AppIcon :icon="active.icon" class="size-3" />
            </div>
            <span class="truncate font-semibold">{{ active.name }}</span>
            <ChevronDownIcon class="opacity-50" />
          </SidebarMenuButton>
        </DropdownMenuTrigger>
        <DropdownMenuContent class="w-64 rounded-lg" align="start" side="bottom" :side-offset="4">
          <DropdownMenuLabel class="text-xs text-muted-foreground">Робочі простори</DropdownMenuLabel>
          <DropdownMenuItem
            v-for="(ws, i) in workspaces"
            :key="ws.name"
            class="gap-2 p-2"
            @click="select(ws)"
          >
            <div class="flex size-6 items-center justify-center rounded-xs border text-sm">
              <AppIcon :icon="ws.icon" class="size-4 shrink-0" />
            </div>
            <span class="truncate">{{ ws.name }}</span>
            <DropdownMenuShortcut>⌘{{ i + 1 }}</DropdownMenuShortcut>
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem class="gap-2 p-2" @click="router.push('/')">
            <div class="flex size-6 items-center justify-center rounded-md border bg-background">
              <PlusIcon class="size-4" />
            </div>
            <span class="font-medium text-muted-foreground">На головну</span>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </SidebarMenuItem>
  </SidebarMenu>
</template>
