<script setup lang="ts">
import { computed } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'

const props = defineProps<{
  workspaceName: string
  doctype?: string
  docId?: string | null
}>()

const wsStore = useWorkspaceStore()

const workspaceLabel = computed(() => wsStore.active?.label ?? props.workspaceName)
const workspaceIcon = computed(() => wsStore.active?.icon ?? '')

const doctypeLabel = computed(() => {
  if (!props.doctype || !wsStore.active) return props.doctype
  const item = wsStore.active.items.find(i => i.link_to === props.doctype)
  return item?.label ?? props.doctype
})
</script>

<template>
  <Breadcrumb class="mb-2">
    <BreadcrumbList>
      <BreadcrumbItem>
        <BreadcrumbLink as-child>
          <router-link :to="`/${workspaceName}`" class="flex items-center gap-1.5 capitalize">
            <span v-if="workspaceIcon" class="text-sm">{{ workspaceIcon }}</span>
            <span class="font-medium">{{ workspaceLabel }}</span>
          </router-link>
        </BreadcrumbLink>
      </BreadcrumbItem>

      <template v-if="doctype">
        <BreadcrumbSeparator />
        <BreadcrumbItem>
          <template v-if="docId">
            <BreadcrumbLink as-child>
              <router-link :to="`/${workspaceName}/list/${doctype}`">
                {{ doctypeLabel }}
              </router-link>
            </BreadcrumbLink>
          </template>
          <template v-else>
            <BreadcrumbPage class="font-semibold text-foreground/90">{{ doctypeLabel }}</BreadcrumbPage>
          </template>
        </BreadcrumbItem>
      </template>

      <template v-if="docId">
        <BreadcrumbSeparator />
        <BreadcrumbItem>
          <BreadcrumbPage class="font-semibold text-foreground/90 truncate max-w-[300px]">{{ docId }}
          </BreadcrumbPage>
        </BreadcrumbItem>
      </template>
    </BreadcrumbList>
  </Breadcrumb>
</template>
