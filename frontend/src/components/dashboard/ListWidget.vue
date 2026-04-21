<script setup lang="ts">
import type { DashboardWidget } from '@/types'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

const props = defineProps<{
  widget: DashboardWidget
  data: { items: Record<string, unknown>[]; title_field: string | null } | null
  loading?: boolean
  workspaceName?: string
}>()

const router = useRouter()
const { t } = useI18n()

function formatDate(val: unknown): string {
  if (!val) return ''
  const d = new Date(val as string)
  if (isNaN(d.getTime())) return String(val)
  return d.toLocaleDateString('uk-UA', { day: '2-digit', month: '2-digit', year: '2-digit' })
}

function getTitle(item: Record<string, unknown>): string {
  if (props.data?.title_field && item[props.data.title_field]) {
    return String(item[props.data.title_field])
  }
  return String(item.name ?? item.id ?? '—')
}

function open(item: Record<string, unknown>) {
  if (!props.workspaceName) return
  router.push(`/${props.workspaceName}/${props.widget.doctype}/${item.id}`)
}
</script>

<template>
  <div class="flex flex-col h-full">
    <!-- Header -->
    <div class="px-5 pt-5 pb-2">
      <p class="text-sm text-muted-foreground font-medium">{{ widget.title }}</p>
    </div>

    <!-- Skeleton -->
    <div v-if="loading" class="flex-1 px-5 flex flex-col gap-2">
      <div v-for="i in 5" :key="i" class="h-9 bg-muted animate-pulse rounded" />
    </div>

    <!-- Empty -->
    <div v-else-if="!data?.items?.length"
      class="flex-1 flex items-center justify-center text-muted-foreground text-sm">
      {{ t('No records') }}
    </div>

    <!-- List -->
    <div v-else class="flex-1 overflow-auto">
      <div
        v-for="item in data.items"
        :key="String(item.id)"
        class="flex items-center justify-between px-5 py-2.5 border-b last:border-0
               hover:bg-muted/50 cursor-pointer transition-colors text-sm"
        @click="open(item)"
      >
        <span class="font-medium truncate max-w-[70%]">{{ getTitle(item) }}</span>
        <span class="text-muted-foreground text-xs tabular-nums shrink-0">
          {{ formatDate(item.modified_at) }}
        </span>
      </div>
    </div>
  </div>
</template>
