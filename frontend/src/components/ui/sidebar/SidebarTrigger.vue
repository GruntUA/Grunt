<script setup lang="ts">
import type { HTMLAttributes } from "vue"
import { Menu } from '@lucide/vue'
import { cn } from "@/lib/utils"
import { useSidebar } from "./utils"

const props = defineProps<{
  class?: HTMLAttributes["class"]
}>()

const { toggleSidebar } = useSidebar()
</script>

<template>
  <Button
    data-sidebar="trigger"
    data-slot="sidebar-trigger"
    outlined severity="secondary" size="small"
    :class="cn('h-8! w-8! p-0! flex items-center justify-center rounded-lg shadow-sm border-border bg-card', props.class)"
    @click="toggleSidebar"
    title="Меню"
  >
    <Menu class="size-4 text-foreground/80" />
    <span class="sr-only">Toggle Sidebar</span>
  </Button>
</template>
