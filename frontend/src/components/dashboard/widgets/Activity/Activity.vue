<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { DashboardWidget } from '@/types'
import { FileText, Plus, RefreshCcw, Trash2, Send, Share2, MessageSquare, GitBranch } from '@lucide/vue'
import { useRouter } from 'vue-router'
import { formatDayMonth } from '@/core/datetime'
import { docUrl } from '@/core/workspaceUrl'

const { t } = useI18n()

const props = defineProps<{
  widget: DashboardWidget
  data: { items: ActivityItem[] } | null
  loading?: boolean
  workspaceName?: string
}>()

interface ActivityItem {
  id: string
  doctype: string
  doc_id: string
  action: string
  user: string
  created_at: string
}

const router = useRouter()

function getActionIcon(action: string) {
  switch (action?.toLowerCase()) {
    case 'create':   return Plus
    case 'update':   return RefreshCcw
    case 'delete':   return Trash2
    case 'submit':   return Send
    case 'share':    return Share2
    case 'comment':  return MessageSquare
    case 'workflow': return GitBranch
    default:         return FileText
  }
}

function getActionColor(action: string): string {
  switch (action?.toLowerCase()) {
    case 'create':   return 'text-emerald-600 bg-emerald-500/10'
    case 'update':   return 'text-amber-600 bg-amber-500/10'
    case 'delete':   return 'text-rose-600 bg-rose-500/10'
    case 'submit':   return 'text-blue-600 bg-blue-500/10'
    case 'workflow': return 'text-violet-600 bg-violet-500/10'
    default:         return 'text-muted-foreground bg-muted'
  }
}

function getActionLabel(action: string): string {
  const map: Record<string, string> = {
    create: t('Created'), update: t('Updated'), delete: t('Deleted'),
    submit: t('Submitted'), cancel: t('Cancelled'),
    share: t('Shared'), comment: t('Commented'), workflow: t('Moved'),
  }
  return map[action?.toLowerCase()] ?? action
}

function formatTime(val: string): string {
  if (!val) return ''
  const d = new Date(val)
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return t('just now')
  if (diffMin < 60) return t('{n} min ago', { n: String(diffMin) })
  const diffH = Math.floor(diffMin / 60)
  if (diffH < 24) return t('{n} h ago', { n: String(diffH) })
  return formatDayMonth(d)
}

function goToDoc(item: ActivityItem) {
  router.push(docUrl(item.doctype, item.doc_id, props.workspaceName))
}
</script>

<template>
  <div class="flex flex-col h-full">
    <!-- Header -->
    <div class="px-5 pt-4 pb-2 shrink-0">
      <p class="text-muted-foreground font-medium">{{ widget.title }}</p>
    </div>

    <!-- Skeleton -->
    <div v-if="loading" class="flex-1 px-5 flex flex-col gap-2 py-2">
      <div v-for="i in 4" :key="i" class="h-12 bg-muted animate-pulse rounded-lg" />
    </div>

    <!-- Empty -->
    <div v-else-if="!data?.items?.length"
      class="flex-1 flex items-center justify-center text-muted-foreground">
      {{ t('No activity') }}
    </div>

    <!-- Feed -->
    <div v-else class="flex-1 overflow-auto divide-y divide-border/50">
      <div
        v-for="item in data.items"
        :key="item.id"
        class="flex items-start gap-3 px-5 py-3 hover:bg-muted/30 transition-colors group cursor-pointer"
        @click="goToDoc(item)"
      >
        <!-- Action icon -->
        <div :class="['mt-0.5 size-7 rounded-md flex items-center justify-center shrink-0', getActionColor(item.action)]">
          <component :is="getActionIcon(item.action)" class="size-3.5" />
        </div>

        <!-- Content -->
        <div class="flex-1 min-w-0">
          <div class="flex items-baseline justify-between gap-2">
            <span class="font-semibold text-foreground truncate">{{ item.user }}</span>
            <span class="text-muted-foreground tabular-nums shrink-0">{{ formatTime(item.created_at) }}</span>
          </div>
          <p class="text-muted-foreground mt-0.5 leading-snug">
            <span class="text-foreground/80">{{ getActionLabel(item.action) }}</span>
            <span class="font-medium text-foreground/60 ml-1">{{ item.doctype }}</span>
            <span class="text-primary font-medium ml-1 truncate">{{ item.doc_id }}</span>
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
