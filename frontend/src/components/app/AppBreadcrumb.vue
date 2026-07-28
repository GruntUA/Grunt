<script setup lang="ts">
import { computed } from 'vue'
import { useAppStore } from '@/stores/app'
import { useDocTypeStore } from '@/stores/doctype'
import { useSidebarStore } from '@/stores/sidebar'
import AppIcon from '@/components/AppIcon.vue'
import { ChevronRight, PanelLeft, PanelLeftClose, PanelLeftOpen } from '@lucide/vue'

const props = defineProps<{
  workspaceName: string
  doctype?: string
  docId?: string | null
}>()

const appStore = useAppStore()
const dtStore = useDocTypeStore()
const sidebarStore = useSidebarStore()

const workspaceLabel = computed(() => appStore.active?.label ?? props.workspaceName)
const workspaceIcon = computed(() => appStore.active?.icon ?? '')

const doctypeLabel = computed(() => {
  if (!props.doctype) return ''
  
  // 1. Try to find in cache first (sync)
  const cached = dtStore.cache?.get?.(props.doctype)
  if (cached) return cached.label ?? cached.name

  // 2. Try to find in workspace items
  if (appStore.active) {
    const item = appStore.active.items.find(i => i.link_to === props.doctype)
    if (item) return item.label
  }

  return props.doctype
})

const items = computed(() => {
  const result: Array<{ label?: string; icon?: string; route?: string }> = [
    {
      label: workspaceLabel.value,
      icon: workspaceIcon.value || undefined,
      route: `/${props.workspaceName}`,
    },
  ]
  if (props.doctype) {
    result.push({
      label: doctypeLabel.value,
      route: props.docId ? `/${props.workspaceName}/${props.doctype}` : undefined,
    })
  }
  if (props.docId) {
    result.push({ label: String(props.docId) })
  }
  return result
})

const isCollapsed = computed(() => sidebarStore.isCollapsed)
</script>

<template>
  <div class="flex items-center gap-3 mb-2 px-0 py-0 md:bg-transparent md:border-none">
    <!-- Desktop Sidebar Collapse Trigger -->
    <button
      class="hidden md:flex size-9 items-center justify-center rounded-xl text-muted-foreground/60 hover:text-primary hover:bg-primary/10 border border-transparent hover:border-primary/20 transition-all shrink-0"
      @click="sidebarStore.toggleCollapse"
    >
      <PanelLeftClose v-if="!isCollapsed" class="size-4.5" />
      <PanelLeftOpen v-else class="size-4.5" />
    </button>

    <!-- Custom Mobile Sidebar Trigger -->
    <button
      class="md:hidden size-9 flex items-center justify-center rounded-xl text-muted-foreground/60 hover:text-primary hover:bg-primary/10 transition-all shrink-0 shadow-sm border border-transparent hover:border-primary/20"
      @click="sidebarStore.toggleMobile"
    >
      <PanelLeft class="size-4.5" />
    </button>

    <Breadcrumb class="hidden sm:flex">
      <BreadcrumbList class="flex-nowrap gap-0">
        <template v-for="(item, idx) in items" :key="idx">
          <BreadcrumbSeparator v-if="idx > 0" class="mx-1">
            <ChevronRight class="size-3.5 text-muted-foreground/30" />
          </BreadcrumbSeparator>
          <BreadcrumbItem>
            <BreadcrumbLink v-if="item.route" as-child>
              <router-link :to="item.route" class="flex items-center gap-2 font-semibold text-[13px] hover:text-primary transition-colors">
                <AppIcon v-if="item.icon" :icon="item.icon" class="size-4 shrink-0 text-muted-foreground/60" />
                <span class="truncate max-w-[200px]">{{ item.label }}</span>
              </router-link>
            </BreadcrumbLink>
            <span v-else class="font-black text-foreground text-[13px] truncate max-w-[300px] opacity-90">{{ item.label }}</span>
          </BreadcrumbItem>
        </template>
      </BreadcrumbList>
    </Breadcrumb>

    <!-- Mobile breadcrumb fallback -->
    <Breadcrumb class="flex sm:hidden">
      <BreadcrumbList>
        <BreadcrumbItem>
          <span class="font-black text-foreground text-[14px] truncate max-w-[200px]">{{ items[items.length - 1].label }}</span>
        </BreadcrumbItem>
      </BreadcrumbList>
    </Breadcrumb>
  </div>
</template>
