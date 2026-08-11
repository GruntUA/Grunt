<script setup lang="ts">
import { computed } from 'vue'
import { useAppStore } from '@/stores/app'
import { useDocTypeStore } from '@/stores/doctype'
import AppIcon from '@/components/AppIcon.vue'
import { ChevronRight } from '@lucide/vue'
import { Breadcrumb, BreadcrumbItem, BreadcrumbLink, BreadcrumbList, BreadcrumbSeparator } from '@/components/ui/breadcrumb'
import { SidebarTrigger } from '@/components/ui/sidebar'
import { Badge } from '@/components/ui/badge'
const props = defineProps<{
  workspaceName: string
  doctype?: string
  docId?: string | null
  /** Record count shown next to the last breadcrumb item (e.g. list page total). */
  count?: number | null
}>()

const appStore = useAppStore()
const dtStore = useDocTypeStore()

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

</script>

<template>
  <div class="flex items-center justify-between gap-4 mb-2 px-0 py-0 md:bg-transparent md:border-none">
    <div class="flex items-center gap-3 overflow-hidden">
    <SidebarTrigger class="shrink-0" />

    <Breadcrumb class="hidden sm:flex">
      <BreadcrumbList class="flex-nowrap gap-0">
        <template v-for="(item, idx) in items" :key="idx">
          <BreadcrumbSeparator v-if="idx > 0" class="mx-1">
            <ChevronRight class="size-3.5 text-muted-foreground/30" />
          </BreadcrumbSeparator>
          <BreadcrumbItem>
            <BreadcrumbLink v-if="item.route" as-child>
              <router-link :to="item.route" class="flex items-center gap-2 font-semibold text-sm">
                <AppIcon v-if="item.icon" :icon="item.icon" class="size-4 shrink-0 text-muted-foreground/60" />
                <span class="truncate max-w-[200px]">{{ item.label }}</span>
              </router-link>
            </BreadcrumbLink>
            <span v-else class="font-semibold text-foreground text-sm truncate max-w-[300px]">{{ item.label }}</span>
          </BreadcrumbItem>
        </template>
      </BreadcrumbList>
    </Breadcrumb>

    <!-- Mobile breadcrumb fallback -->
    <Breadcrumb class="flex sm:hidden">
      <BreadcrumbList>
        <BreadcrumbItem>
          <span class="font-semibold text-foreground text-sm truncate max-w-[200px]">{{ items[items.length - 1].label }}</span>
        </BreadcrumbItem>
      </BreadcrumbList>
    </Breadcrumb>

    <Badge v-if="count !== null && count !== undefined" variant="secondary" class="tabular-nums shrink-0">
      {{ count }}
    </Badge>
    </div>

    <div v-if="$slots.actions" class="flex items-center shrink-0">
      <slot name="actions" />
    </div>
  </div>
</template>
