<script setup lang="ts">
/**
 * «Дії ▾» - replaces the primary button while list rows are selected: the
 * `bulk` actions of the registry, «select all N» and «clear selection».
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronDown, CheckCheck, X } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import type { ResolvedAction } from '@/core/actions'
import ActionIcon from './ActionIcon.vue'

const props = defineProps<{
  actions: ResolvedAction[]
  count: number
  total?: number
  allSelected?: boolean
  /** Rows on the current page - «select all N» is offered once all of them are selected. */
  pageCount?: number
}>()

const emit = defineEmits<{
  (e: 'selectAll'): void
  (e: 'clear'): void
}>()

const { t } = useI18n()

const canSelectAll = computed(() =>
  !props.allSelected && !!props.total && props.pageCount != null
  && props.count >= props.pageCount && props.total > props.count,
)
</script>

<template>
  <DropdownMenu>
    <DropdownMenuTrigger as-child>
      <Button size="sm" class="gap-1.5" data-action="bulk">
        {{ t('Actions') }}
        <ChevronDown class="size-3.5 opacity-70" />
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent class="w-56" align="end">
      <DropdownMenuLabel class="font-normal text-muted-foreground">
        <span class="font-semibold text-foreground tabular-nums">
          {{ allSelected ? t('all {n}', { n: String(total ?? count) }) : count }}
        </span>
        {{ t('selected') }}
      </DropdownMenuLabel>
      <DropdownMenuSeparator />
      <DropdownMenuItem
        v-for="action in actions"
        :key="action.id"
        :variant="action.variant === 'destructive' ? 'destructive' : 'default'"
        :disabled="action.disabled || action.busy"
        :data-action="action.id"
        @click="action.run()"
      >
        <ActionIcon v-if="action.icon" :name="action.icon" class="size-4" />
        <span>{{ action.label }}</span>
      </DropdownMenuItem>
      <DropdownMenuSeparator v-if="actions.length" />
      <DropdownMenuItem v-if="canSelectAll" @click="emit('selectAll')">
        <CheckCheck class="size-4" />
        <span>{{ t('Select all {n}', { n: String(total) }) }}</span>
      </DropdownMenuItem>
      <DropdownMenuItem @click="emit('clear')">
        <X class="size-4" />
        <span>{{ t('Clear selection') }}</span>
      </DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>
</template>
