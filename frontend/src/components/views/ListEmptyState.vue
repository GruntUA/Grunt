<script setup lang="ts">
import { computed, inject, type Component } from 'vue'
import { useI18n } from 'vue-i18n'
import { FileSpreadsheet, FunnelX, WifiOff } from '@lucide/vue'
import type { PaginationMeta } from '@/types'
import { LIST_FILTER_RESET } from '@/core/composables/useListFilterReset'
import { Button } from '@/components/ui/button'
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'

/**
 * "No rows" for every list view. Three cases: the data source is down
 * (`meta.unavailable`), filters hide everything (offers a reset - see
 * LIST_FILTER_RESET), or the DocType is simply empty.
 */
const props = withDefaults(defineProps<{
  meta?: Pick<PaginationMeta, 'unavailable' | 'unavailable_message'>
  icon?: Component
}>(), { icon: () => FileSpreadsheet })

const { t } = useI18n()
const filters = inject(LIST_FILTER_RESET, null)

// The backend already knows *why* its data source is unavailable (Redis down,
// an external API unreachable, …) and hands over ready-to-display text - we
// just render it, with a neutral fallback if none was given.
const unavailable = computed(() =>
  props.meta?.unavailable ? props.meta.unavailable_message || t('The data source is temporarily unavailable.') : null,
)
</script>

<template>
  <Empty>
    <EmptyHeader v-if="unavailable">
      <EmptyMedia variant="icon"><WifiOff /></EmptyMedia>
      <EmptyTitle>{{ t('Data source unavailable') }}</EmptyTitle>
      <EmptyDescription>{{ unavailable }}</EmptyDescription>
    </EmptyHeader>

    <template v-else-if="filters?.active.value">
      <EmptyHeader>
        <EmptyMedia variant="icon"><FunnelX /></EmptyMedia>
        <EmptyTitle>{{ t('No records match your filters') }}</EmptyTitle>
        <EmptyDescription>{{ t('Try adjusting your filters to see more results.') }}</EmptyDescription>
      </EmptyHeader>
      <EmptyContent>
        <Button variant="outline" size="sm" @click="filters.clear()">{{ t('Clear Filters') }}</Button>
      </EmptyContent>
    </template>

    <EmptyHeader v-else>
      <EmptyMedia variant="icon"><component :is="icon" /></EmptyMedia>
      <EmptyTitle>{{ t('No records found') }}</EmptyTitle>
    </EmptyHeader>
  </Empty>
</template>
