<script setup lang="ts">
import { computed } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'
import { useDocTypeStore } from '@/stores/doctype'
import { SidebarTrigger } from '@/components/ui/sidebar'
import { ChevronRight } from '@lucide/vue'

const props = defineProps<{
  workspaceName: string
  doctype?: string
  docId?: string | null
}>()

const wsStore = useWorkspaceStore()
const dtStore = useDocTypeStore()

const workspaceLabel = computed(() => wsStore.active?.label ?? props.workspaceName)
const workspaceIcon = computed(() => wsStore.active?.icon ?? '')

const doctypeLabel = computed(() => {
  if (!props.doctype) return ''
  
  // 1. Try to find in cache first (sync)
  const cached = dtStore.cache?.get?.(props.doctype)
  if (cached) return cached.label ?? cached.name

  // 2. Try to find in workspace items
  if (wsStore.active) {
    const item = wsStore.active.items.find(i => i.link_to === props.doctype)
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
      route: props.docId ? `/${props.workspaceName}/list/${props.doctype}` : undefined,
    })
  }
  if (props.docId) {
    result.push({ label: String(props.docId) })
  }
  return result
})
</script>

<template>
  <div class="flex items-center gap-1.5 mb-2 sm:mb-1 -ml-1 sm:ml-0">
    <SidebarTrigger class="md:hidden shrink-0 text-muted-foreground/80 hover:text-foreground" />
    <Breadcrumb :model="items" class="bg-transparent! border-none! p-0! hidden sm:flex">
    <template #separator>
      <ChevronRight class="size-3 text-muted-foreground/50 mx-0.5" />
    </template>
    <template #item="{ item, props: ip }">
      <router-link
        v-if="item.route"
        v-slot="rp"
        :to="item.route"
        custom
      >
        <a v-bind="ip.action" :href="rp.href" class="flex items-center gap-1.5 font-medium" @click="rp.navigate">
          <span v-if="item.icon" class="text-sm shrink-0">{{ item.icon }}</span>
          <span class="truncate max-w-[200px]">{{ item.label }}</span>
        </a>
      </router-link>
      <span v-else class="font-bold text-foreground truncate max-w-[300px] opacity-90">{{ item.label }}</span>
    </template>
  </Breadcrumb>
  
  <!-- Mobile breadcrumb fallback if needed or just show the active part -->
  <Breadcrumb :model="items.slice(-1)" class="!bg-transparent !border-none !p-0 flex sm:hidden">
    <template #item="{ item }">
      <span class="font-bold text-foreground truncate max-w-[200px]">{{ item.label }}</span>
    </template>
  </Breadcrumb>
  </div>
</template>
