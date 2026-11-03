<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { Check, Copy, ExternalLink } from '@lucide/vue'
import type { SidebarRow } from '@/core/api/docs'
import { statusToneClass } from '@/core/status'
import { useToast } from '@/core/composables/useToast'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

// label -> value rows from the server's sidebar_sections (grunt.document.sidebar):
// the property list at the top and every app section render through this.
const props = defineProps<{ rows: SidebarRow[] }>()

const { t } = useI18n()
const toast = useToast()

const copied = ref<number | null>(null)
async function copy(i: number, value: SidebarRow['value']) {
  try {
    await navigator.clipboard.writeText(String(value ?? ''))
    copied.value = i
    setTimeout(() => (copied.value = null), 1500)
  } catch {
    toast.error(t('Could not copy'))
  }
}

// A desk path opens in place; a URL - or a path marked external (a website page) - in a new tab.
const items = computed(() =>
  props.rows.map((row) => {
    if (!row.link) return { row, is: 'span', attrs: {}, external: false }
    if (row.link.startsWith('/') && !row.external) return { row, is: RouterLink, attrs: { to: row.link }, external: false }
    return { row, is: 'a', attrs: { href: row.link, target: '_blank', rel: 'noopener' }, external: true }
  }),
)
</script>

<template>
  <dl class="grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-4 gap-y-2.5">
    <template v-for="({ row, is, attrs, external }, i) in items" :key="i">
      <dt class="text-muted-foreground">{{ row.label }}</dt>
      <dd class="flex min-w-0 items-center gap-1">
        <Tooltip :disabled="!row.tooltip">
          <TooltipTrigger as-child>
            <component
              :is="is"
              v-bind="attrs"
              class="group flex min-w-0 items-center gap-1"
              :class="row.link && 'rounded-sm outline-none hover:text-primary focus-visible:ring-2 focus-visible:ring-ring/50'"
            >
              <Badge v-if="row.indicator" variant="outline" :class="statusToneClass(row.indicator)">{{ row.value }}</Badge>
              <span v-else class="truncate" :class="row.mono && 'font-mono text-xs'">{{ row.value ?? '' }}</span>
              <ExternalLink v-if="external" class="size-3 shrink-0 text-muted-foreground group-hover:text-primary" />
            </component>
          </TooltipTrigger>
          <TooltipContent class="max-w-80 break-all">{{ row.tooltip }}</TooltipContent>
        </Tooltip>
        <Tooltip v-if="row.copy">
          <TooltipTrigger as-child>
            <Button variant="ghost" size="icon-xs" class="text-muted-foreground" :aria-label="t('Copy')" @click="copy(i, row.value)">
              <Check v-if="copied === i" class="text-success" />
              <Copy v-else />
            </Button>
          </TooltipTrigger>
          <TooltipContent>{{ copied === i ? t('Copied') : t('Copy') }}</TooltipContent>
        </Tooltip>
      </dd>
    </template>
  </dl>
</template>
