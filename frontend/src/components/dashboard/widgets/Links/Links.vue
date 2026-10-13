<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import type { DashboardWidget } from '@/types'
import { appUrl } from '@/core/workspaceUrl'
import type { WorkspaceLinkItem } from '@/core/api/workspace'
import { Item, ItemContent, ItemDescription, ItemGroup, ItemMedia, ItemTitle } from '@/components/ui/item'

const props = defineProps<{
  widget: DashboardWidget
  workspaceName?: string
}>()

const router = useRouter()
const { t } = useI18n()

const links = computed<WorkspaceLinkItem[]>(() => {
  try {
    return JSON.parse(props.widget.content || '[]')
  } catch {
    return []
  }
})

function navigate(link: WorkspaceLinkItem) {
  if (link.type === 'URL') window.open(link.link_to, '_blank')
  else router.push(appUrl({ type: link.type, name: link.link_to, workspace: props.workspaceName }))
}
</script>

<template>
  <div class="p-4 h-full flex flex-col">
    <h3 v-if="widget.title" class="font-semibold text-foreground mb-3">
      {{ widget.title }}
    </h3>

    <ItemGroup v-if="links.length" class="grid grid-cols-2 sm:grid-cols-3 gap-2">
      <Item
        v-for="link in links"
        :key="link.link_to"
        as="button"
        variant="outline"
        size="sm"
        class="text-left hover:bg-accent"
        @click="navigate(link)"
      >
        <ItemMedia v-if="link.icon" class="text-lg">{{ link.icon }}</ItemMedia>
        <ItemContent class="min-w-0">
          <ItemTitle class="w-full truncate">{{ link.label }}</ItemTitle>
          <ItemDescription v-if="link.description" class="truncate">{{ link.description }}</ItemDescription>
        </ItemContent>
      </Item>
    </ItemGroup>

    <p v-else class="text-muted-foreground/60 italic">{{ t('No links') }}</p>
  </div>
</template>
