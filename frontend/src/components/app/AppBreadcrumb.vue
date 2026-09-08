<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAppStore } from '@/stores/app'
import { useDocTypeStore } from '@/stores/doctype'
import AppIcon from '@/components/AppIcon.vue'
import { ChevronRight } from '@lucide/vue'
import { Breadcrumb, BreadcrumbItem, BreadcrumbLink, BreadcrumbList, BreadcrumbSeparator } from '@/components/ui/breadcrumb'
import { SidebarTrigger } from '@/components/ui/sidebar'
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
const props = defineProps<{
  workspaceName: string
  doctype?: string
  docId?: string | null
  /** Human title for the document — replaces the raw id as the last crumb. */
  docLabel?: string | null
  /** Record count shown next to the last breadcrumb item (e.g. list page total). */
  count?: number | null
  /** New (unsaved) document form: link the DocType crumb to the list and add a "New …" terminal crumb. */
  isNew?: boolean
}>()

const appStore = useAppStore()
const dtStore = useDocTypeStore()
const { t } = useI18n()

const workspaceLabel = computed(() => appStore.active?.label ?? props.workspaceName)
const workspaceIcon = computed(() => appStore.active?.icon ?? '')

const doctypeLabel = computed(() => {
  if (!props.doctype) return ''

  // 1. Prefer the workspace nav label so the crumb matches the sidebar (e.g. "Активи").
  const item = appStore.active?.items.find(i => i.link_to === props.doctype)
  if (item?.label) return item.label

  // 2. Fall back to the DocType meta label from cache.
  const cached = dtStore.cache?.get?.(props.doctype)
  if (cached) return cached.label ?? cached.name

  return props.doctype
})

// Shown as a native hover tooltip on the DocType breadcrumb item.
const doctypeDescription = computed(
  () => (props.doctype && dtStore.cache?.get?.(props.doctype)?.description) || undefined,
)

const doctypeIcon = computed(() => {
  if (!props.doctype) return undefined
  const fromCache = dtStore.cache?.get?.(props.doctype)?.icon
  if (fromCache) return fromCache
  const item = appStore.active?.items.find(i => i.link_to === props.doctype)
  return item?.icon || undefined
})

const items = computed(() => {
  const result: Array<{ label?: string; icon?: string; route?: string; title?: string }> = [
    {
      label: workspaceLabel.value,
      icon: workspaceIcon.value || undefined,
      route: `/${props.workspaceName}`,
    },
  ]
  if (props.doctype) {
    result.push({
      label: doctypeLabel.value,
      icon: doctypeIcon.value,
      // Link back to the list whenever the DocType crumb is not the current page.
      route: props.docId || props.isNew ? `/${props.workspaceName}/${props.doctype}` : undefined,
      title: doctypeDescription.value,
    })
  }
  if (props.docId) {
    const label = props.docLabel?.trim() || String(props.docId)
    result.push({
      label,
      title: label !== String(props.docId) ? String(props.docId) : undefined,
    })
  } else if (props.isNew && props.doctype) {
    result.push({ label: props.docLabel?.trim() || t('New') })
  }
  return result
})

</script>

<template>
  <div class="flex items-center justify-between gap-4 mb-2 px-0 py-0 md:bg-transparent md:border-none">
    <div class="flex items-center gap-3 overflow-hidden">
    <SidebarTrigger class="shrink-0" />

    <Breadcrumb class="hidden sm:flex min-w-0">
      <BreadcrumbList class="flex-nowrap gap-0 min-w-0">
        <template v-for="(item, idx) in items" :key="idx">
          <BreadcrumbSeparator v-if="idx > 0" class="mx-1 shrink-0">
            <ChevronRight class="size-3.5 text-muted-foreground/30" />
          </BreadcrumbSeparator>
          <BreadcrumbItem :class="idx === items.length - 1 ? 'min-w-0' : 'shrink-0'">
            <Tooltip :disabled="!item.title" :delay-duration="300">
              <TooltipTrigger as-child>
                <BreadcrumbLink v-if="item.route" as-child>
                  <router-link :to="item.route" class="flex items-center gap-2 font-semibold">
                    <AppIcon v-if="item.icon" :icon="item.icon" class="size-4 shrink-0 text-muted-foreground/60" />
                    <span class="truncate max-w-[200px]">{{ item.label }}</span>
                  </router-link>
                </BreadcrumbLink>
                <span v-else class="flex items-center gap-2 font-semibold text-foreground truncate min-w-0">
                  <AppIcon v-if="item.icon" :icon="item.icon" class="size-4 shrink-0 text-muted-foreground/60" />
                  {{ item.label }}
                </span>
              </TooltipTrigger>
              <TooltipContent side="bottom" class="max-w-xs">{{ item.title }}</TooltipContent>
            </Tooltip>
          </BreadcrumbItem>
        </template>
      </BreadcrumbList>
    </Breadcrumb>

    <!-- Mobile breadcrumb fallback -->
    <Breadcrumb class="flex sm:hidden">
      <BreadcrumbList>
        <BreadcrumbItem>
          <span class="font-semibold text-foreground truncate max-w-[200px]">{{ items[items.length - 1].label }}</span>
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
