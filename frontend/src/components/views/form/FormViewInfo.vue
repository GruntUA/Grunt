<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery } from '@tanstack/vue-query'
import { Eye } from '@lucide/vue'
import { docsApi } from '@/core/api/docs'
import type { DocType } from '@/types'

// Seen / views line under the form; only fetched when the DocType opts into
// track_seen / track_views.
const props = defineProps<{ dt: DocType; id: string }>()

const { t } = useI18n()

const MAX_SHOWN = 6

const enabled = computed(() => !!(props.dt.track_seen || props.dt.track_views))
const { data: info } = useQuery({
  queryKey: computed(() => ['view-info', props.dt.name, props.id]),
  queryFn: () => docsApi.getViewInfo(props.dt.name, props.id),
  enabled,
})
const seen = computed(() => (props.dt.track_seen ? info.value?.seen ?? [] : []))
const seenShown = computed(() => seen.value.slice(0, MAX_SHOWN))
</script>

<template>
  <div v-if="enabled && info" class="flex flex-wrap items-center gap-x-4 gap-y-1.5 px-1 text-muted-foreground">
    <span v-if="dt.track_views" class="inline-flex items-center gap-1.5">
      <Eye class="size-3.5" />
      {{ t('{views} views · {viewers} users', { views: String(info.views), viewers: String(info.viewers) }) }}
    </span>
    <span v-if="seen.length" class="inline-flex items-center gap-1.5">
      {{ t('Viewed by:') }}
      <span class="flex -space-x-1.5">
        <span v-for="email in seenShown" :key="email" :title="email"
          class="inline-flex size-5 items-center justify-center rounded-full border border-background bg-muted text-[9px] font-medium text-foreground">
          {{ email.slice(0, 2).toUpperCase() }}
        </span>
      </span>
      <span v-if="seen.length > seenShown.length">+{{ seen.length - seenShown.length }}</span>
    </span>
  </div>
</template>
