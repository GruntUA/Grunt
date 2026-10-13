<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DashboardWidget, ShortcutItem } from '@/types'
import { ExternalLink } from '@lucide/vue'
import { useRouter } from 'vue-router'
import { appUrl } from '@/core/workspaceUrl'
import { useLucideIcons } from '@/core/composables/useLucideIcons'
import { Item, ItemContent, ItemMedia, ItemTitle } from '@/components/ui/item'

const props = defineProps<{
  widget: DashboardWidget
  workspaceName?: string
}>()

const router = useRouter()
const { t } = useI18n()
const { iconFor } = useLucideIcons()

const tiles = computed<ShortcutItem[]>(() => {
  try { return JSON.parse(props.widget.content ?? '[]') } catch { return [] }
})

const colorMap: Record<string, string> = {
  primary: 'bg-primary/10 text-primary',
  blue: 'bg-blue-500/10 text-blue-600',
  amber: 'bg-amber-500/10 text-amber-600',
  red: 'bg-red-500/10 text-red-600',
  violet: 'bg-violet-500/10 text-violet-600',
  cyan: 'bg-cyan-500/10 text-cyan-600',
}

function navigate(tile: ShortcutItem) {
  const ws = props.workspaceName ?? ''
  if (tile.link_type === 'URL') {
    window.open(tile.link_to, '_blank')
  } else {
    router.push(appUrl({ type: tile.link_type, name: tile.link_to, workspace: ws }))
  }
}
</script>

<template>
  <div class="flex flex-col h-full">
    <div v-if="widget.title" class="px-5 pt-4 pb-2">
      <p class="text-muted-foreground font-medium">{{ widget.title }}</p>
    </div>
    <div class="grid grid-cols-[repeat(auto-fit,minmax(11rem,1fr))] gap-2 p-3">
      <Item
        v-for="(tile, i) in tiles"
        :key="i"
        as="button"
        variant="outline"
        size="sm"
        class="min-w-0 text-left hover:bg-accent"
        @click="navigate(tile)">
        <ItemMedia variant="icon" :class="['border-0', colorMap[tile.color ?? 'primary'] ?? colorMap.primary]">
          <component :is="iconFor(tile.icon, ExternalLink) ?? 'span'" />
        </ItemMedia>
        <ItemContent class="min-w-0">
          <ItemTitle class="w-full truncate">{{ tile.title }}</ItemTitle>
        </ItemContent>
      </Item>
      <div v-if="tiles.length === 0"
        class="col-span-full flex items-center justify-center text-muted-foreground py-4">
        {{ t('No tiles') }}
      </div>
    </div>
  </div>
</template>
