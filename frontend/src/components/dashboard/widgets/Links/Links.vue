<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import type { DashboardWidget } from '@/types'
import { appUrl } from '@/core/workspaceUrl'
import type { WorkspaceLinkItem } from '@/core/api/workspace'

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

    <div v-if="links.length" class="grid grid-cols-2 sm:grid-cols-3 gap-2">
      <button
        v-for="link in links"
        :key="link.link_to"
        class="flex items-center gap-2 px-3 py-2.5 rounded-lg border border-border bg-background hover:border-primary hover:bg-accent text-left transition-colors group"
        @click="navigate(link)"
      >
        <span v-if="link.icon" class="text-lg shrink-0">{{ link.icon }}</span>
        <div class="min-w-0">
          <p class="font-medium text-foreground truncate">{{ link.label }}</p>
          <p v-if="link.description" class="text-muted-foreground truncate">
            {{ link.description }}
          </p>
        </div>
      </button>
    </div>

    <p v-else class="text-muted-foreground/60 italic">{{ t('No links') }}</p>
  </div>
</template>
